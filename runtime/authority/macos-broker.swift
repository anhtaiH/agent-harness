import CryptoKit
import Darwin
import Foundation
import LocalAuthentication
import Security

enum BrokerFailure: Error, CustomStringConvertible {
    case invalidRequest(String)
    case capability(String)
    case security(String, OSStatus)

    var description: String {
        switch self {
        case .invalidRequest(let message), .capability(let message):
            return message
        case .security(let operation, let status):
            let detail = SecCopyErrorMessageString(status, nil) as String? ?? "unknown"
            return "\(operation) failed: \(status) (\(detail))"
        }
    }
}

enum FixedLocator {
    static let approvalKey = "agent-harness.authority.approval-key.v1"
    static let anchor = "agent-harness.authority.anchor.v1"
    static let receiptKey = "agent-harness.authority.broker-receipt-key.v1"
    static let bootstrapRecord = "agent-harness.authority.bootstrap-record.v1"
    static let terminalPin = "agent-harness.authority.terminal-pin.v1"
}

struct BootstrapRequest: Decodable {
    let installationId: UUID
    let creatorId: String
    let brokerCodeIdentity: String
    let brokerContentDigest: String
    let descriptorDigest: String
    let finalPlanDigest: String
    let walDigest: String
    let anchorNamespace: String
    let initialAnchorGeneration: Int
    let initialAnchorCommitment: String
}

struct RetirementPinRequest: Decodable {
    let installationId: UUID
    let authorityEra: String
    let attestationDigest: String
    let receiptPublicKeyDigest: String
    let helperObjectIdentity: String
    let helperFinalizerDigest: String
}

struct BootstrapManifest: Encodable {
    let installationId: String
    let brokerCodeIdentity: String
    let brokerContentDigest: String
    let approvalPublicKeyDigest: String
    let approvalPersistentReference: String
    let anchorNamespace: String
    let receiptPublicKeyDigest: String
    let receiptPersistentReference: String
    let bootstrapDigest: String
    let pendingPlanCommitment: String
}

private let maximumRequestBytes = 1_048_576

func requireHexDigest(_ value: String, field: String) throws {
    guard value.count == 64,
          value.utf8.allSatisfy({ byte in
              (48...57).contains(byte) || (97...102).contains(byte)
          }) else {
        throw BrokerFailure.invalidRequest("\(field) must be lowercase SHA-256")
    }
}

func readBoundedStdin() throws -> Data {
    guard isatty(STDIN_FILENO) == 1 else {
        throw BrokerFailure.capability(
            "authority mutation requires protected local interactive stdin"
        )
    }
    var result = Data()
    while true {
        let chunk = FileHandle.standardInput.readData(ofLength: 16_384)
        if chunk.isEmpty { break }
        result.append(chunk)
        if result.count > maximumRequestBytes {
            throw BrokerFailure.invalidRequest("authority request exceeds size limit")
        }
    }
    guard !result.isEmpty else {
        throw BrokerFailure.invalidRequest("authority request is empty")
    }
    return result
}

func requireProtectedUserPresence(reason: String) throws {
    let context = LAContext()
    var evaluationError: NSError?
    guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &evaluationError)
    else {
        throw BrokerFailure.capability(
            "protected user presence unavailable: \(evaluationError?.localizedDescription ?? "unknown")"
        )
    }
    let semaphore = DispatchSemaphore(value: 0)
    var accepted = false
    var failure: Error?
    context.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) {
        success, error in
        accepted = success
        failure = error
        semaphore.signal()
    }
    semaphore.wait()
    guard accepted else {
        throw BrokerFailure.capability(
            "protected user presence denied: \(failure?.localizedDescription ?? "unknown")"
        )
    }
}

func sha256(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

func keyPersistentReference(tag: Data) throws -> Data {
    let query: [CFString: Any] = [
        kSecClass: kSecClassKey,
        kSecAttrApplicationTag: tag,
        kSecReturnPersistentRef: true,
        kSecMatchLimit: kSecMatchLimitOne,
    ]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    guard status == errSecSuccess, let reference = result as? Data else {
        throw BrokerFailure.security("read key persistent reference", status)
    }
    return reference
}

func addSecureEnclaveKey(
    locator: String,
    protectedUserPresence: Bool
) throws -> (publicDigest: String, persistentReference: String) {
    let flags: SecAccessControlCreateFlags = protectedUserPresence
        ? [.privateKeyUsage, .userPresence] : [.privateKeyUsage]
    var accessError: Unmanaged<CFError>?
    guard let access = SecAccessControlCreateWithFlags(
        nil,
        kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        flags,
        &accessError
    ) else {
        throw BrokerFailure.capability(
            "cannot create protected key access control: \(String(describing: accessError?.takeRetainedValue()))"
        )
    }
    let tag = Data(locator.utf8)
    let attributes: [CFString: Any] = [
        kSecAttrKeyType: kSecAttrKeyTypeECSECPrimeRandom,
        kSecAttrKeySizeInBits: 256,
        kSecAttrTokenID: kSecAttrTokenIDSecureEnclave,
        kSecPrivateKeyAttrs: [
            kSecAttrIsPermanent: true,
            kSecAttrApplicationTag: tag,
            kSecAttrAccessControl: access,
        ],
    ]
    var keyError: Unmanaged<CFError>?
    guard let privateKey = SecKeyCreateRandomKey(
        attributes as CFDictionary, &keyError
    ) else {
        throw BrokerFailure.capability(
            "Secure Enclave P-256 key unavailable or fixed locator collided: \(String(describing: keyError?.takeRetainedValue()))"
        )
    }
    guard let publicKey = SecKeyCopyPublicKey(privateKey) else {
        throw BrokerFailure.capability("Secure Enclave public key unavailable")
    }
    var exportError: Unmanaged<CFError>?
    guard let publicBytes = SecKeyCopyExternalRepresentation(
        publicKey, &exportError
    ) as Data? else {
        throw BrokerFailure.capability(
            "public key export failed: \(String(describing: exportError?.takeRetainedValue()))"
        )
    }
    let persistentReference = try keyPersistentReference(tag: tag)
    return (sha256(publicBytes), persistentReference.base64EncodedString())
}

func addGenericPassword(
    locator: String,
    payload: Data,
    accessibility: CFString
) throws {
    let query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: locator,
        kSecAttrAccount: locator,
        kSecAttrSynchronizable: false,
        kSecAttrAccessible: accessibility,
        kSecValueData: payload,
    ]
    let status = SecItemAdd(query as CFDictionary, nil)
    guard status == errSecSuccess else {
        throw BrokerFailure.security(
            "add-only Keychain item \(locator)", status
        )
    }
}

func canonicalJSON<T: Encodable>(_ value: T) throws -> Data {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    return try encoder.encode(value)
}

func bootstrap(_ request: BootstrapRequest) throws -> BootstrapManifest {
    guard request.initialAnchorGeneration == 0 else {
        throw BrokerFailure.invalidRequest("initial anchor generation must be zero")
    }
    try requireHexDigest(request.brokerContentDigest, field: "brokerContentDigest")
    try requireHexDigest(request.descriptorDigest, field: "descriptorDigest")
    try requireHexDigest(request.finalPlanDigest, field: "finalPlanDigest")
    try requireHexDigest(request.walDigest, field: "walDigest")
    try requireHexDigest(
        request.initialAnchorCommitment, field: "initialAnchorCommitment"
    )
    try requireProtectedUserPresence(
        reason: "Create Agent Harness protected local authority"
    )

    let approval = try addSecureEnclaveKey(
        locator: FixedLocator.approvalKey,
        protectedUserPresence: true
    )
    let receipt = try addSecureEnclaveKey(
        locator: FixedLocator.receiptKey,
        protectedUserPresence: false
    )
    let anchorPayload = try JSONSerialization.data(
        withJSONObject: [
            "installation_id": request.installationId.uuidString.lowercased(),
            "creator_id": request.creatorId,
            "namespace": request.anchorNamespace,
            "generation": request.initialAnchorGeneration,
            "commitment": request.initialAnchorCommitment,
            "descriptor_digest": request.descriptorDigest,
            "final_plan_digest": request.finalPlanDigest,
            "wal_digest": request.walDigest,
        ],
        options: [.sortedKeys]
    )
    try addGenericPassword(
        locator: FixedLocator.anchor,
        payload: anchorPayload,
        accessibility: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
    )
    let recordPayload = try JSONSerialization.data(
        withJSONObject: [
            "installation_id": request.installationId.uuidString.lowercased(),
            "creator_id": request.creatorId,
            "broker_code_identity": request.brokerCodeIdentity,
            "broker_content_digest": request.brokerContentDigest,
            "descriptor_digest": request.descriptorDigest,
            "final_plan_digest": request.finalPlanDigest,
            "wal_digest": request.walDigest,
        ],
        options: [.sortedKeys]
    )
    try addGenericPassword(
        locator: FixedLocator.bootstrapRecord,
        payload: recordPayload,
        accessibility: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
    )
    return BootstrapManifest(
        installationId: request.installationId.uuidString.lowercased(),
        brokerCodeIdentity: request.brokerCodeIdentity,
        brokerContentDigest: request.brokerContentDigest,
        approvalPublicKeyDigest: approval.publicDigest,
        approvalPersistentReference: approval.persistentReference,
        anchorNamespace: request.anchorNamespace,
        receiptPublicKeyDigest: receipt.publicDigest,
        receiptPersistentReference: receipt.persistentReference,
        bootstrapDigest: request.descriptorDigest,
        pendingPlanCommitment: request.finalPlanDigest
    )
}

func addRetirementPin(_ request: RetirementPinRequest) throws {
    try requireHexDigest(request.attestationDigest, field: "attestationDigest")
    try requireHexDigest(
        request.receiptPublicKeyDigest, field: "receiptPublicKeyDigest"
    )
    try requireHexDigest(
        request.helperFinalizerDigest, field: "helperFinalizerDigest"
    )
    try requireProtectedUserPresence(
        reason: "Finalize Agent Harness authority retirement"
    )
    let payload = try JSONSerialization.data(
        withJSONObject: [
            "installation_id": request.installationId.uuidString.lowercased(),
            "authority_era": request.authorityEra,
            "attestation_digest": request.attestationDigest,
            "receipt_public_key_digest": request.receiptPublicKeyDigest,
            "helper_object_identity": request.helperObjectIdentity,
            "helper_finalizer_digest": request.helperFinalizerDigest,
        ],
        options: [.sortedKeys]
    )
    try addGenericPassword(
        locator: FixedLocator.terminalPin,
        payload: payload,
        accessibility: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
    )
}

func selfTest() throws {
    let locators = [
        FixedLocator.approvalKey,
        FixedLocator.anchor,
        FixedLocator.receiptKey,
        FixedLocator.bootstrapRecord,
        FixedLocator.terminalPin,
    ]
    guard Set(locators).count == locators.count,
          locators.allSatisfy({ !$0.isEmpty }) else {
        throw BrokerFailure.capability("fixed authority locators are invalid")
    }
    let sample = Data("self-test".utf8)
    guard sha256(sample).count == 64 else {
        throw BrokerFailure.capability("SHA-256 unavailable")
    }
    print(
        "{\"keychain_mutated\":false,\"ok\":true,\"user_presence_requested\":false}"
    )
}

do {
    let arguments = Array(CommandLine.arguments.dropFirst())
    guard arguments.count == 1 else {
        throw BrokerFailure.invalidRequest(
            "usage: macos-broker --self-test|bootstrap|retirement-pin"
        )
    }
    switch arguments[0] {
    case "--self-test":
        try selfTest()
    case "bootstrap":
        let request = try JSONDecoder().decode(
            BootstrapRequest.self, from: readBoundedStdin()
        )
        let manifest = try bootstrap(request)
        FileHandle.standardOutput.write(try canonicalJSON(manifest))
        FileHandle.standardOutput.write(Data([0x0a]))
    case "retirement-pin":
        let request = try JSONDecoder().decode(
            RetirementPinRequest.self, from: readBoundedStdin()
        )
        try addRetirementPin(request)
        print("{\"ok\":true}")
    default:
        throw BrokerFailure.invalidRequest("unsupported authority operation")
    }
} catch {
    FileHandle.standardError.write(Data("authority broker: \(error)\n".utf8))
    exit(1)
}
