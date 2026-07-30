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
    static let integrityKey = "agent-harness.signing-key.v1"
}

indirect enum JSONValue: Codable {
    case object([String: JSONValue])
    case array([JSONValue])
    case string(String)
    case integer(Int)
    case number(Double)
    case boolean(Bool)
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .boolean(value)
        } else if let value = try? container.decode(Int.self) {
            self = .integer(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            self = .object(
                try container.decode([String: JSONValue].self)
            )
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .object(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .string(let value): try container.encode(value)
        case .integer(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .boolean(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }
}

struct BootstrapRequest: Codable {
    let createdAt: String
    let installationId: UUID
    let creatorId: String
    let descriptorDigest: String
    let finalPlanDigest: String
    let finalPlan: [String: JSONValue]
    let walDigest: String
    let anchorNamespace: String
    let initialAnchorGeneration: Int
    let initialAnchorCommitment: String
    let bootstrapAuthorization: String
}

struct RetirementPinRequest: Codable {
    let installationId: UUID
    let authorityEra: String
    let attestationDigest: String
    let receiptPublicKeyDigest: String
    let helperObjectIdentity: String
    let helperFinalizerDigest: String
    let brokerSignature: String?
}

struct TerminalPinAttributes: Codable {
    let addOnly: Bool
    let containsKeyMaterial: Bool
    let synchronizable: Bool
    let accessibility: String
}

struct BootstrapManifest: Encodable {
    let schema: String
    let schemaVersion: Int
    let createdAt: String
    let installationId: String
    let brokerCodeIdentity: String
    let brokerContentDigest: String
    let approvalPublicKeyDigest: String
    let approvalPersistentReference: String
    let anchorBackendId: String
    let anchorNamespace: String
    let receiptKeyId: String
    let receiptPublicKeyDigest: String
    let receiptPersistentReference: String
    let integrityKeyId: String
    let integrityKeyLocator: String
    let integrityPersistentReference: String
    let terminalPinLocator: String
    let terminalPinAttributes: TerminalPinAttributes
    let capabilityState: [String]
    let bootstrapDigest: String
    let pendingPlanCommitment: String
    let brokerSignature: String?
}

struct BrokerAttestation: Encodable {
    let protocolVersion: Int
    let codeIdentity: String
    let contentDigest: String
}

struct AnchorReadRequest: Decodable {
    let namespace: String
}

struct AnchorState: Codable, Equatable {
    let namespace: String
    let generation: Int
    let commitment: String
}

struct AnchorCASRequest: Decodable {
    let domain: String
    let transitionDomain: String
    let transitionDigest: String
    let namespace: String
    let installationId: String
    let subjectKind: String
    let subjectId: String
    let operationKind: String
    let oldGeneration: Int
    let oldCommitment: String
    let newGeneration: Int
    let newCommitment: String
    let planDigest: String
    let walDigest: String
    let eventDigest: String
    let checkDigest: String
    let recordDigest: String
    let authorizationEpoch: Int
    let callerCodeIdentity: String
    let brokerCodeIdentity: String
    let nonce: String
    let expiresAt: Int
    let authorizationMac: String
}

struct AnchorTransitionAuthorization: Codable {
    let domain: String
    let namespace: String
    let installationId: String
    let subjectKind: String
    let subjectId: String
    let operationKind: String
    let oldGeneration: Int
    let oldCommitment: String
    let newGeneration: Int
    let newCommitment: String
    let planDigest: String
    let walDigest: String
    let eventDigest: String
    let checkDigest: String
    let recordDigest: String
    let authorizationEpoch: Int
    let callerCodeIdentity: String
    let brokerCodeIdentity: String
    let nonce: String
    let expiresAt: Int
}

struct AnchorReceipt: Codable {
    let schema: String
    let schemaVersion: Int
    let createdAt: String
    let installationId: String
    let anchorNamespace: String
    let anchorBackendId: String
    let receiptKeyId: String
    let transitionDomain: String
    let transitionDigest: String
    let oldGeneration: Int
    let oldCommitment: String
    let newGeneration: Int
    let newCommitment: String
    let operationId: String
    var brokerReceipt: String?
}

struct ReceiptVerifyRequest: Decodable {
    let payloadBase64: String
    let signature: String
}

struct ApprovalSignRequest: Decodable {
    let envelopeBase64: String
    let summary: String
}

struct ExternalWriteEnvelope: Decodable {
    let schema: String
    let schemaVersion: Int
    let installationId: String
    let intentDigest: String
    let predecessorTaskEventHash: String
    let expiresAt: String
}

struct BootstrapRecordIdentity: Decodable {
    let installationId: String
}

struct ApprovalSignature: Codable, Equatable {
    let algorithm: String
    let publicKeyDigest: String
    let envelopeDigest: String
    let summaryDigest: String
    let signature: String
}

struct ApprovalVerifyRequest: Decodable {
    let envelopeBase64: String
    let summary: String
    let approval: ApprovalSignature
}

struct BoolResponse: Encodable {
    let valid: Bool
}

struct HealthResponse: Encodable {
    let healthy: Bool
    let codeIdentity: String
    let contentDigest: String
    let approvalPublicKeyDigest: String
    let userPresenceAvailable: Bool
}

private let maximumRequestBytes = 1_048_576
private let authorityLockPath = "/var/tmp/agent-harness-authority.v1.lock"
private let bootstrapCapabilityDomain = Data(
    "agent-harness/native-bootstrap-capability/v1\0".utf8
)
private let setupBodyDomain = Data(
    "agent-harness/setup-body/v1\0".utf8
)
private let bootstrapDescriptorDomain = Data(
    "agent-harness/authority-bootstrap-descriptor/v1\0".utf8
)
private let finalInstallPlanDomain = Data(
    "agent-harness/final-install-plan/v1\0".utf8
)

func requireHexDigest(_ value: String, field: String) throws {
    guard value.count == 64,
          value.utf8.allSatisfy({ byte in
              (48...57).contains(byte) || (97...102).contains(byte)
          }) else {
        throw BrokerFailure.invalidRequest("\(field) must be lowercase SHA-256")
    }
}

func hexadecimalData(_ value: String) -> Data? {
    guard value.count % 2 == 0 else { return nil }
    var bytes = Data()
    bytes.reserveCapacity(value.count / 2)
    var index = value.startIndex
    while index < value.endIndex {
        let next = value.index(index, offsetBy: 2)
        guard let byte = UInt8(value[index..<next], radix: 16) else {
            return nil
        }
        bytes.append(byte)
        index = next
    }
    return bytes
}

func readBoundedStdin() throws -> Data {
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

func readBootstrapCapability() throws -> Data {
    guard let encoded = ProcessInfo.processInfo.environment[
              "AGENT_HARNESS_BOOTSTRAP_CAPABILITY_FD"
          ],
          let descriptor = Int32(encoded) else {
        throw BrokerFailure.capability(
            "verified bootstrap authorization required"
        )
    }
    defer { close(descriptor) }
    var bytes = [UInt8](repeating: 0, count: 33)
    let count = Darwin.read(descriptor, &bytes, bytes.count)
    guard count == 32 else {
        throw BrokerFailure.capability(
            "verified bootstrap authorization required"
        )
    }
    return Data(bytes.prefix(Int(count)))
}

func authenticatedBootstrapRequest(
    from data: Data,
    capability: () throws -> Data = readBootstrapCapability
) throws -> BootstrapRequest {
    guard let original = try JSONSerialization.jsonObject(with: data)
              as? [String: Any] else {
        throw BrokerFailure.invalidRequest(
            "bootstrap request must be an object"
        )
    }
    let expectedFields: Set<String> = [
        "created_at",
        "installation_id",
        "creator_id",
        "descriptor_digest",
        "final_plan_digest",
        "final_plan",
        "wal_digest",
        "anchor_namespace",
        "initial_anchor_generation",
        "initial_anchor_commitment",
        "bootstrap_authorization",
    ]
    guard Set(original.keys) == expectedFields,
          let authorization = original["bootstrap_authorization"] as? String,
          let authorizationBytes = hexadecimalData(authorization) else {
        throw BrokerFailure.capability(
            "verified bootstrap authorization required"
        )
    }
    let canonical = try JSONSerialization.data(
        withJSONObject: original,
        options: [.sortedKeys, .withoutEscapingSlashes]
    )
    guard canonical == data else {
        throw BrokerFailure.invalidRequest(
            "bootstrap request must be canonical JSON"
        )
    }
    var unsigned = original
    unsigned.removeValue(forKey: "bootstrap_authorization")
    let payload = try JSONSerialization.data(
        withJSONObject: unsigned,
        options: [.sortedKeys, .withoutEscapingSlashes]
    )
    let secret = try capability()
    guard secret.count == 32,
          HMAC<SHA256>.isValidAuthenticationCode(
              authorizationBytes,
              authenticating: bootstrapCapabilityDomain + payload,
              using: SymmetricKey(data: secret)
          ) else {
        throw BrokerFailure.capability(
            "verified bootstrap authorization required"
        )
    }
    return try decodeRequest(BootstrapRequest.self, from: data)
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

func currentExecutableURL() throws -> URL {
    var capacity: UInt32 = 0
    _ = _NSGetExecutablePath(nil, &capacity)
    var buffer = [CChar](repeating: 0, count: Int(capacity))
    let result = buffer.withUnsafeMutableBufferPointer {
        _NSGetExecutablePath($0.baseAddress, &capacity)
    }
    guard result == 0 else {
        throw BrokerFailure.capability("derive broker executable path")
    }
    let executable = URL(fileURLWithPath: String(cString: buffer))
        .resolvingSymlinksInPath()
        .standardizedFileURL
    guard executable.path.hasPrefix("/") else {
        throw BrokerFailure.capability("broker executable path is not absolute")
    }
    return executable
}

func brokerAttestation() throws -> BrokerAttestation {
    let executable = try currentExecutableURL()
    let contentDigest = sha256(try Data(contentsOf: executable))
    var selfCode: SecCode?
    var status = SecCodeCopySelf([], &selfCode)
    guard status == errSecSuccess, let selfCode else {
        throw BrokerFailure.security("derive broker code identity", status)
    }
    var staticCode: SecStaticCode?
    status = SecCodeCopyStaticCode(selfCode, [], &staticCode)
    guard status == errSecSuccess, let staticCode else {
        throw BrokerFailure.security("derive broker static code", status)
    }
    var requirement: SecRequirement?
    status = SecCodeCopyDesignatedRequirement(staticCode, [], &requirement)
    guard status == errSecSuccess, let requirement else {
        throw BrokerFailure.security(
            "derive broker designated requirement", status
        )
    }
    var requirementText: CFString?
    status = SecRequirementCopyString(requirement, [], &requirementText)
    guard status == errSecSuccess, let requirementText else {
        throw BrokerFailure.security(
            "serialize broker designated requirement", status
        )
    }
    return BrokerAttestation(
        protocolVersion: 1,
        codeIdentity: "designated:\(requirementText)",
        contentDigest: contentDigest
    )
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

func currentApplicationAccess() throws -> SecAccess {
    var trustedApplication: SecTrustedApplication?
    let executable = try currentExecutableURL()
    var status = executable.path.withCString {
        SecTrustedApplicationCreateFromPath($0, &trustedApplication)
    }
    guard status == errSecSuccess, let trustedApplication else {
        throw BrokerFailure.security(
            "create broker trusted application", status
        )
    }
    var access: SecAccess?
    status = SecAccessCreate(
        "Agent Harness native authority" as CFString,
        [trustedApplication] as CFArray,
        &access
    )
    guard status == errSecSuccess, let access else {
        throw BrokerFailure.security("create broker key access", status)
    }
    return access
}

func addSecureEnclaveKey(
    locator: String,
    marker: String,
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
    var privateAttributes: [CFString: Any] = [
        kSecAttrLabel: marker,
        kSecAttrIsPermanent: true,
        kSecAttrApplicationTag: tag,
    ]
    if protectedUserPresence {
        privateAttributes[kSecAttrAccessControl] = access
    } else {
        privateAttributes[kSecAttrAccess] = try currentApplicationAccess()
    }
    let attributes: [CFString: Any] = [
        kSecAttrKeyType: kSecAttrKeyTypeECSECPrimeRandom,
        kSecAttrKeySizeInBits: 256,
        kSecAttrTokenID: kSecAttrTokenIDSecureEnclave,
        kSecPrivateKeyAttrs: privateAttributes,
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

func existingSecureEnclaveKey(
    locator: String,
    marker: String
) throws -> (publicDigest: String, persistentReference: String)? {
    let tag = Data(locator.utf8)
    let query: [CFString: Any] = [
        kSecClass: kSecClassKey,
        kSecAttrApplicationTag: tag,
        kSecReturnAttributes: true,
        kSecReturnRef: true,
        kSecMatchLimit: kSecMatchLimitOne,
    ]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    if status == errSecItemNotFound {
        return nil
    }
    guard status == errSecSuccess,
          let attributes = result as? [CFString: Any],
          attributes[kSecAttrLabel] as? String == marker,
          let privateKey = attributes[kSecValueRef] as! SecKey? else {
        throw BrokerFailure.capability(
            "foreign fixed-locator collision at \(locator)"
        )
    }
    guard let publicKey = SecKeyCopyPublicKey(privateKey) else {
        throw BrokerFailure.capability("Secure Enclave public key unavailable")
    }
    var error: Unmanaged<CFError>?
    guard let publicBytes = SecKeyCopyExternalRepresentation(
        publicKey, &error
    ) as Data? else {
        throw BrokerFailure.capability(
            "public key export failed: \(String(describing: error?.takeRetainedValue()))"
        )
    }
    let reference = try keyPersistentReference(tag: tag)
    return (sha256(publicBytes), reference.base64EncodedString())
}

func ensureSecureEnclaveKey(
    locator: String,
    marker: String,
    protectedUserPresence: Bool
) throws -> (publicDigest: String, persistentReference: String) {
    if let existing = try existingSecureEnclaveKey(
        locator: locator, marker: marker
    ) {
        return existing
    }
    return try addSecureEnclaveKey(
        locator: locator,
        marker: marker,
        protectedUserPresence: protectedUserPresence
    )
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

func ensureGenericPassword(
    locator: String,
    payload: Data,
    accessibility: CFString
) throws {
    do {
        let existing = try readGenericPassword(locator: locator)
        guard existing == payload else {
            throw BrokerFailure.capability(
                "foreign fixed-locator collision at \(locator)"
            )
        }
    } catch BrokerFailure.security(_, let status)
        where status == errSecItemNotFound {
        try addGenericPassword(
            locator: locator,
            payload: payload,
            accessibility: accessibility
        )
    }
}

func genericPasswordExists(locator: String) throws -> Bool {
    do {
        _ = try readGenericPassword(locator: locator)
        return true
    } catch BrokerFailure.security(_, let status)
        where status == errSecItemNotFound {
        return false
    }
}

func existingIntegrityKey(
    marker: String
) throws -> (key: Data, persistentReference: String)? {
    let query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: FixedLocator.integrityKey,
        kSecAttrAccount: FixedLocator.integrityKey,
        kSecReturnAttributes: true,
        kSecReturnData: true,
        kSecReturnPersistentRef: true,
        kSecMatchLimit: kSecMatchLimitOne,
    ]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    if status == errSecItemNotFound {
        return nil
    }
    guard status == errSecSuccess,
          let attributes = result as? [CFString: Any],
          attributes[kSecAttrLabel] as? String == marker,
          let key = attributes[kSecValueData] as? Data,
          key.count == 32,
          let reference = attributes[kSecValuePersistentRef] as? Data else {
        throw BrokerFailure.capability(
            "foreign fixed-locator collision at \(FixedLocator.integrityKey)"
        )
    }
    return (key, reference.base64EncodedString())
}

func ensureIntegrityKey(
    marker: String
) throws -> (key: Data, persistentReference: String) {
    if let existing = try existingIntegrityKey(marker: marker) {
        return existing
    }
    var key = Data(count: 32)
    let randomStatus = key.withUnsafeMutableBytes {
        SecRandomCopyBytes(kSecRandomDefault, 32, $0.baseAddress!)
    }
    guard randomStatus == errSecSuccess else {
        throw BrokerFailure.security(
            "generate integrity key", randomStatus
        )
    }
    let query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: FixedLocator.integrityKey,
        kSecAttrAccount: FixedLocator.integrityKey,
        kSecAttrLabel: marker,
        kSecAttrSynchronizable: false,
        kSecAttrAccessible:
            kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        kSecAttrAccess: try currentApplicationAccess(),
        kSecValueData: key,
    ]
    let status = SecItemAdd(query as CFDictionary, nil)
    guard status == errSecSuccess else {
        throw BrokerFailure.security(
            "add-only Keychain item \(FixedLocator.integrityKey)", status
        )
    }
    guard let added = try existingIntegrityKey(marker: marker),
          added.key == key else {
        throw BrokerFailure.capability(
            "integrity key exact readback failed"
        )
    }
    return added
}

func canonicalJSON<T: Encodable>(_ value: T) throws -> Data {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    encoder.keyEncodingStrategy = .convertToSnakeCase
    return try encoder.encode(value)
}

func decodeRequest<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    return try decoder.decode(type, from: data)
}

func canonicalJSONObject(_ value: Any) throws -> Data {
    guard JSONSerialization.isValidJSONObject(value) else {
        throw BrokerFailure.invalidRequest("bootstrap plan is malformed")
    }
    return try JSONSerialization.data(
        withJSONObject: value,
        options: [.sortedKeys, .withoutEscapingSlashes]
    )
}

func domainDigest(_ domain: Data, _ value: Any) throws -> String {
    sha256(domain + (try canonicalJSONObject(value)))
}

func validateBootstrapPlan(
    _ request: BootstrapRequest,
    attestation: BrokerAttestation
) throws -> Data {
    let planData = try canonicalJSON(request.finalPlan)
    guard let plan = try JSONSerialization.jsonObject(with: planData)
              as? [String: Any] else {
        throw BrokerFailure.invalidRequest("final install plan is malformed")
    }
    let planFields: Set<String> = [
        "schema",
        "schema_version",
        "created_at",
        "installation_id",
        "runtime_root",
        "rollback_root",
        "source_commit",
        "source_content_identity",
        "setup_body_digest",
        "authority_bootstrap",
        "authority_bootstrap_digest",
        "adapter_plan_digests",
        "operations",
        "plan_digest",
    ]
    guard Set(plan.keys) == planFields,
          plan["schema"] as? String == "agent-harness/install-plan",
          plan["schema_version"] as? Int == 1,
          let createdAt = plan["created_at"] as? String,
          let installationId = plan["installation_id"] as? String,
          UUID(uuidString: installationId) == request.installationId,
          let runtimeRoot = plan["runtime_root"] as? String,
          runtimeRoot.hasPrefix("/"),
          let rollbackRoot = plan["rollback_root"] as? String,
          rollbackRoot.hasPrefix("/"),
          let source = plan["source_content_identity"]
              as? [String: Any],
          let sourceCommit = source["source_commit"] as? String,
          plan["source_commit"] as? String == sourceCommit,
          let adapterDigests = plan["adapter_plan_digests"] as? [Any],
          let operations = plan["operations"] as? [Any],
          let descriptor = plan["authority_bootstrap"]
              as? [String: Any],
          let setupDigest = plan["setup_body_digest"] as? String,
          let descriptorDigest =
              plan["authority_bootstrap_digest"] as? String,
          let planDigest = plan["plan_digest"] as? String else {
        throw BrokerFailure.invalidRequest(
            "final install plan fields mismatch"
        )
    }
    let sourceFields: Set<String> = [
        "algorithm",
        "algorithm_version",
        "inclusion_policy",
        "policy_version",
        "ordered_manifest_digest",
        "source_commit",
        "frozen_snapshot_digest",
        "digest",
        "entries",
    ]
    guard sourceFields.isSubset(of: Set(source.keys)),
          createdAt == request.createdAt,
          installationId
              == request.installationId.uuidString.lowercased(),
          planDigest == request.finalPlanDigest,
          descriptorDigest == request.descriptorDigest else {
        throw BrokerFailure.invalidRequest(
            "final install plan request binding mismatch"
        )
    }
    for (name, value) in [
        ("setup_body_digest", setupDigest),
        ("authority_bootstrap_digest", descriptorDigest),
        ("plan_digest", planDigest),
    ] {
        try requireHexDigest(value, field: name)
    }
    for value in adapterDigests {
        guard let digest = value as? String else {
            throw BrokerFailure.invalidRequest(
                "adapter plan digests are malformed"
            )
        }
        try requireHexDigest(digest, field: "adapter_plan_digest")
    }

    let setupBody: [String: Any] = [
        "installation_id": installationId,
        "runtime_root": runtimeRoot,
        "rollback_root": rollbackRoot,
        "source_identity": source,
        "adapter_plan_digests": adapterDigests,
        "operations": operations,
    ]
    guard try domainDigest(setupBodyDomain, setupBody) == setupDigest else {
        throw BrokerFailure.invalidRequest("setup-body digest mismatch")
    }

    let descriptorFields: Set<String> = [
        "setup_body_digest",
        "installation_id",
        "creator_id",
        "broker_locator",
        "broker_code_identity",
        "broker_content_digest",
        "wal_locator",
        "locators",
        "item_attributes",
        "capabilities",
        "conditional_inverses",
        "initial_anchor",
    ]
    guard Set(descriptor.keys) == descriptorFields,
          descriptor["setup_body_digest"] as? String == setupDigest,
          descriptor["installation_id"] as? String == installationId,
          descriptor["creator_id"] as? String == request.creatorId,
          let brokerLocator = descriptor["broker_locator"] as? String,
          brokerLocator.hasPrefix("/"),
          descriptor["broker_code_identity"] as? String
              == attestation.codeIdentity,
          descriptor["broker_content_digest"] as? String
              == attestation.contentDigest,
          let walLocator = descriptor["wal_locator"] as? String,
          walLocator.hasPrefix("/"),
          let locators = descriptor["locators"] as? [String: Any],
          let attributes = descriptor["item_attributes"]
              as? [String: Any],
          let capabilities = descriptor["capabilities"] as? [Any],
          let inverses = descriptor["conditional_inverses"] as? [Any],
          let anchor = descriptor["initial_anchor"] as? [String: Any]
          else {
        throw BrokerFailure.invalidRequest(
            "authority bootstrap descriptor fields mismatch"
        )
    }
    let expectedLocators: [String: Any] = [
        "approval_key": FixedLocator.approvalKey,
        "anchor": FixedLocator.anchor,
        "receipt_key": FixedLocator.receiptKey,
        "integrity_key": FixedLocator.integrityKey,
        "bootstrap_record": FixedLocator.bootstrapRecord,
        "terminal_pin": FixedLocator.terminalPin,
    ]
    let expectedAttributes: [String: Any] = [
        "approval_key": [
            "key_type": "SecureEnclaveP256",
            "non_exportable": true,
            "synchronizable": false,
            "accessibility": "WhenUnlockedThisDeviceOnly",
            "access_control": ["privateKeyUsage", "userPresence"],
        ],
        "anchor": [
            "non_exportable": true,
            "synchronizable": false,
            "accessibility": "AfterFirstUnlockThisDeviceOnly",
            "code_identity_restricted": true,
        ],
        "receipt_key": [
            "key_type": "P256",
            "non_exportable": true,
            "synchronizable": false,
            "accessibility": "AfterFirstUnlockThisDeviceOnly",
            "code_identity_restricted": true,
        ],
        "integrity_key": [
            "key_type": "HMAC-SHA256",
            "non_exportable": true,
            "synchronizable": false,
            "accessibility": "AfterFirstUnlockThisDeviceOnly",
            "code_identity_restricted": true,
        ],
        "bootstrap_record": [
            "add_only": true,
            "contains_key_material": false,
            "synchronizable": false,
            "accessibility": "AfterFirstUnlockThisDeviceOnly",
        ],
        "terminal_pin": [
            "add_only": true,
            "contains_key_material": false,
            "synchronizable": false,
            "accessibility": "AfterFirstUnlockThisDeviceOnly",
        ],
    ]
    let expectedCapabilities: [Any] = [
        "protected-user-presence-approval",
        "installation-anchor-cas",
        "broker-signed-receipts",
        "retirement-terminal-pin-add",
    ]
    let inverseMarkers: [Any] = [
        "installation_id",
        "creator_id",
        "broker_code_identity",
        "bootstrap_digest",
        "wal_digest",
    ]
    let expectedInverses: [Any] = [
        FixedLocator.approvalKey,
        FixedLocator.anchor,
        FixedLocator.receiptKey,
        FixedLocator.integrityKey,
        FixedLocator.bootstrapRecord,
    ].map {
        [
            "operation": "remove-exact-add-result",
            "locator": $0,
            "requires_markers": inverseMarkers,
        ] as [String: Any]
    }
    guard try canonicalJSONObject(locators)
              == canonicalJSONObject(expectedLocators),
          try canonicalJSONObject(attributes)
              == canonicalJSONObject(expectedAttributes),
          try canonicalJSONObject(capabilities)
              == canonicalJSONObject(expectedCapabilities),
          try canonicalJSONObject(inverses)
              == canonicalJSONObject(expectedInverses),
          Set(anchor.keys) == [
              "namespace", "generation", "commitment",
          ],
          anchor["namespace"] as? String == request.anchorNamespace,
          anchor["generation"] as? Int == request.initialAnchorGeneration,
          anchor["commitment"] as? String
              == request.initialAnchorCommitment,
          request.initialAnchorGeneration == 0 else {
        throw BrokerFailure.invalidRequest(
            "authority bootstrap descriptor policy mismatch"
        )
    }
    guard try domainDigest(bootstrapDescriptorDomain, descriptor)
              == descriptorDigest else {
        throw BrokerFailure.invalidRequest(
            "authority bootstrap descriptor digest mismatch"
        )
    }
    var unsignedPlan = plan
    unsignedPlan.removeValue(forKey: "plan_digest")
    guard try domainDigest(finalInstallPlanDomain, unsignedPlan)
              == planDigest else {
        throw BrokerFailure.invalidRequest(
            "final install-plan digest mismatch"
        )
    }
    try requireHexDigest(request.walDigest, field: "walDigest")
    try requireHexDigest(
        request.initialAnchorCommitment,
        field: "initialAnchorCommitment"
    )
    return try canonicalJSONObject([
        "schema": "agent-harness/native-bootstrap-approval",
        "schema_version": 1,
        "installation_id": installationId,
        "creator_id": request.creatorId,
        "setup_body_digest": setupDigest,
        "descriptor_digest": descriptorDigest,
        "final_plan_digest": planDigest,
        "wal_digest": request.walDigest,
        "broker_code_identity": attestation.codeIdentity,
        "broker_content_digest": attestation.contentDigest,
    ])
}

func withAuthorityLock<T>(_ operation: () throws -> T) throws -> T {
    let descriptor = open(
        authorityLockPath,
        O_CREAT | O_RDWR | O_NOFOLLOW,
        S_IRUSR | S_IWUSR
    )
    guard descriptor >= 0 else {
        throw BrokerFailure.capability("cannot open native authority lock")
    }
    defer { close(descriptor) }
    guard flock(descriptor, LOCK_EX) == 0 else {
        throw BrokerFailure.capability("cannot acquire native authority lock")
    }
    defer { flock(descriptor, LOCK_UN) }
    return try operation()
}

func readGenericPassword(locator: String) throws -> Data {
    let query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: locator,
        kSecAttrAccount: locator,
        kSecReturnData: true,
        kSecMatchLimit: kSecMatchLimitOne,
    ]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    guard status == errSecSuccess, let data = result as? Data else {
        throw BrokerFailure.security("read Keychain item \(locator)", status)
    }
    return data
}

func updateGenericPassword(locator: String, payload: Data) throws {
    let query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: locator,
        kSecAttrAccount: locator,
    ]
    let status = SecItemUpdate(
        query as CFDictionary,
        [kSecValueData: payload] as CFDictionary
    )
    guard status == errSecSuccess else {
        throw BrokerFailure.security("update Keychain item \(locator)", status)
    }
}

func keyReference(locator: String) throws -> SecKey {
    let query: [CFString: Any] = [
        kSecClass: kSecClassKey,
        kSecAttrApplicationTag: Data(locator.utf8),
        kSecReturnRef: true,
        kSecMatchLimit: kSecMatchLimitOne,
    ]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    guard status == errSecSuccess, let key = result as! SecKey? else {
        throw BrokerFailure.security("read authority key \(locator)", status)
    }
    return key
}

func publicKeyDigest(locator: String) throws -> String {
    let privateKey = try keyReference(locator: locator)
    guard let publicKey = SecKeyCopyPublicKey(privateKey) else {
        throw BrokerFailure.capability("authority public key is unavailable")
    }
    var error: Unmanaged<CFError>?
    guard let bytes = SecKeyCopyExternalRepresentation(
        publicKey, &error
    ) as Data? else {
        throw BrokerFailure.capability(
            "authority public key export failed: \(String(describing: error?.takeRetainedValue()))"
        )
    }
    return sha256(bytes)
}

func signPayload(locator: String, payload: Data) throws -> Data {
    let privateKey = try keyReference(locator: locator)
    let algorithm = SecKeyAlgorithm.ecdsaSignatureMessageX962SHA256
    guard SecKeyIsAlgorithmSupported(privateKey, .sign, algorithm) else {
        throw BrokerFailure.capability("authority signature algorithm unavailable")
    }
    var error: Unmanaged<CFError>?
    guard let signature = SecKeyCreateSignature(
        privateKey, algorithm, payload as CFData, &error
    ) as Data? else {
        throw BrokerFailure.capability(
            "authority signing failed: \(String(describing: error?.takeRetainedValue()))"
        )
    }
    return signature
}

func verifyPayload(
    locator: String,
    payload: Data,
    signature: Data
) throws -> Bool {
    let privateKey = try keyReference(locator: locator)
    guard let publicKey = SecKeyCopyPublicKey(privateKey) else {
        throw BrokerFailure.capability("authority public key is unavailable")
    }
    var error: Unmanaged<CFError>?
    return SecKeyVerifySignature(
        publicKey,
        .ecdsaSignatureMessageX962SHA256,
        payload as CFData,
        signature as CFData,
        &error
    )
}

func anchorState(expectedNamespace: String) throws -> AnchorState {
    let state = try decodeRequest(
        AnchorState.self,
        from: readGenericPassword(locator: FixedLocator.anchor)
    )
    guard state.namespace == expectedNamespace else {
        throw BrokerFailure.capability("anchor namespace mismatch")
    }
    return state
}

func requireTransitionAuthorization(_ request: AnchorCASRequest) throws {
    guard request.domain == "installation-transaction",
          request.transitionDomain == request.domain,
          request.subjectKind == "task",
          request.operationKind == "publish-installation",
          UUID(uuidString: request.installationId) != nil,
          !request.namespace.isEmpty,
          !request.subjectId.isEmpty,
          !request.callerCodeIdentity.isEmpty,
          !request.nonce.isEmpty,
          request.authorizationEpoch >= 0,
          request.expiresAt > Int(Date().timeIntervalSince1970) else {
        throw BrokerFailure.capability(
            "authenticated anchor transition required"
        )
    }
    for (value, field) in [
        (request.oldCommitment, "oldCommitment"),
        (request.newCommitment, "newCommitment"),
        (request.planDigest, "planDigest"),
        (request.walDigest, "walDigest"),
        (request.eventDigest, "eventDigest"),
        (request.checkDigest, "checkDigest"),
        (request.recordDigest, "recordDigest"),
        (request.transitionDigest, "transitionDigest"),
    ] {
        try requireHexDigest(value, field: field)
    }
    let attestation = try brokerAttestation()
    guard request.brokerCodeIdentity == attestation.codeIdentity else {
        throw BrokerFailure.capability(
            "authenticated anchor transition required"
        )
    }
    let anchorTransition = AnchorTransitionAuthorization(
        domain: request.domain,
        namespace: request.namespace,
        installationId: request.installationId,
        subjectKind: request.subjectKind,
        subjectId: request.subjectId,
        operationKind: request.operationKind,
        oldGeneration: request.oldGeneration,
        oldCommitment: request.oldCommitment,
        newGeneration: request.newGeneration,
        newCommitment: request.newCommitment,
        planDigest: request.planDigest,
        walDigest: request.walDigest,
        eventDigest: request.eventDigest,
        checkDigest: request.checkDigest,
        recordDigest: request.recordDigest,
        authorizationEpoch: request.authorizationEpoch,
        callerCodeIdentity: request.callerCodeIdentity,
        brokerCodeIdentity: request.brokerCodeIdentity,
        nonce: request.nonce,
        expiresAt: request.expiresAt
    )
    let encoded = try canonicalJSON(anchorTransition)
    var transitionPayload = Data(
        "agent-harness/verified-anchor-transition/v1\0".utf8
    )
    transitionPayload.append(encoded)
    guard request.transitionDigest == sha256(transitionPayload) else {
        throw BrokerFailure.capability(
            "authenticated anchor transition required"
        )
    }
    guard let suppliedMac = hexadecimalData(request.authorizationMac) else {
        throw BrokerFailure.capability(
            "authenticated anchor transition required"
        )
    }
    var macPayload = Data(
        "agent-harness/mac/anchor-transition-request/v1\0".utf8
    )
    macPayload.append(encoded)
    let integrityKey = SymmetricKey(
        data: try readGenericPassword(locator: FixedLocator.integrityKey)
    )
    guard HMAC<SHA256>.isValidAuthenticationCode(
        suppliedMac,
        authenticating: macPayload,
        using: integrityKey
    ) else {
        throw BrokerFailure.capability(
            "authenticated anchor transition required"
        )
    }
}

func compareAndAdvance(_ request: AnchorCASRequest) throws -> AnchorReceipt {
    return try withAuthorityLock {
        try requireTransitionAuthorization(request)
        func cachedReceipt(from data: Data) throws -> AnchorReceipt? {
            guard let record = try JSONSerialization.jsonObject(with: data)
                      as? [String: Any],
                  let value = record["last_receipt"] as? [String: Any] else {
                return nil
            }
            var receipt = try decodeRequest(
                AnchorReceipt.self,
                from: canonicalJSONObject(value)
            )
            guard receipt.schema == "agent-harness/state-anchor-receipt",
                  receipt.schemaVersion == 1,
                  receipt.installationId == request.installationId,
                  receipt.anchorNamespace == request.namespace,
                  receipt.anchorBackendId == "native-keychain-anchor-v1",
                  receipt.receiptKeyId
                      == "broker-receipt:\(request.installationId)",
                  receipt.transitionDomain == request.transitionDomain,
                  receipt.transitionDigest == request.transitionDigest,
                  receipt.oldGeneration == request.oldGeneration,
                  receipt.oldCommitment == request.oldCommitment,
                  receipt.newGeneration == request.newGeneration,
                  receipt.newCommitment == request.newCommitment,
                  receipt.operationId == request.nonce,
                  let encodedSignature = receipt.brokerReceipt,
                  let signature = Data(base64Encoded: encodedSignature)
                  else {
                return nil
            }
            receipt.brokerReceipt = nil
            guard try verifyPayload(
                locator: FixedLocator.receiptKey,
                payload: canonicalJSON(receipt),
                signature: signature
            ) else {
                return nil
            }
            receipt.brokerReceipt = encodedSignature
            return receipt
        }

        let currentData = try readGenericPassword(
            locator: FixedLocator.anchor
        )
        let current = try decodeRequest(AnchorState.self, from: currentData)
        guard current.namespace == request.namespace else {
            throw BrokerFailure.capability("anchor namespace mismatch")
        }
        if current.generation == request.newGeneration,
           current.commitment == request.newCommitment,
           let recovered = try cachedReceipt(from: currentData) {
            return recovered
        }
        guard current.generation == request.oldGeneration,
              current.commitment == request.oldCommitment else {
            throw BrokerFailure.capability("stale anchor generation or commitment")
        }
        guard request.newGeneration == request.oldGeneration + 1 else {
            throw BrokerFailure.invalidRequest(
                "anchor transition must advance exactly one generation"
            )
        }
        try requireHexDigest(request.newCommitment, field: "newCommitment")
        try requireHexDigest(request.transitionDigest, field: "transitionDigest")
        let next = AnchorState(
            namespace: request.namespace,
            generation: request.newGeneration,
            commitment: request.newCommitment
        )
        var receipt = AnchorReceipt(
            schema: "agent-harness/state-anchor-receipt",
            schemaVersion: 1,
            createdAt: ISO8601DateFormatter().string(from: Date()),
            installationId: request.installationId,
            anchorNamespace: request.namespace,
            anchorBackendId: "native-keychain-anchor-v1",
            receiptKeyId: "broker-receipt:\(request.installationId)",
            transitionDomain: request.transitionDomain,
            transitionDigest: request.transitionDigest,
            oldGeneration: request.oldGeneration,
            oldCommitment: request.oldCommitment,
            newGeneration: request.newGeneration,
            newCommitment: request.newCommitment,
            operationId: request.nonce,
            brokerReceipt: nil
        )
        receipt.brokerReceipt = try signPayload(
            locator: FixedLocator.receiptKey,
            payload: canonicalJSON(receipt)
        ).base64EncodedString()
        let receiptObject = try JSONSerialization.jsonObject(
            with: canonicalJSON(receipt)
        )
        let anchorRecord: [String: Any] = [
            "namespace": next.namespace,
            "generation": next.generation,
            "commitment": next.commitment,
            "last_receipt": receiptObject,
        ]
        try updateGenericPassword(
            locator: FixedLocator.anchor,
            payload: canonicalJSONObject(anchorRecord)
        )
        let readbackData = try readGenericPassword(
            locator: FixedLocator.anchor
        )
        let readback = try decodeRequest(
            AnchorState.self,
            from: readbackData
        )
        guard readback == next,
              let durableReceipt = try cachedReceipt(from: readbackData)
              else {
            throw BrokerFailure.capability(
                "anchor and receipt durable readback failed"
            )
        }
        return durableReceipt
    }
}

func requireApprovalEnvelope(_ envelope: Data) throws {
    guard let object = try JSONSerialization.jsonObject(with: envelope)
              as? [String: Any],
          Set(object.keys) == [
              "schema",
              "schema_version",
              "installation_id",
              "intent_digest",
              "predecessor_task_event_hash",
              "expires_at",
          ],
          try canonicalJSONObject(object) == envelope else {
        throw BrokerFailure.invalidRequest(
            "version-one external-write envelope required"
        )
    }
    let document = try decodeRequest(ExternalWriteEnvelope.self, from: envelope)
    guard document.schema == "agent-harness/external-write-envelope",
          document.schemaVersion == 1,
          UUID(uuidString: document.installationId) != nil,
          document.expiresAt.hasSuffix("Z") else {
        throw BrokerFailure.invalidRequest(
            "version-one external-write envelope required"
        )
    }
    try requireHexDigest(document.intentDigest, field: "intentDigest")
    try requireHexDigest(
        document.predecessorTaskEventHash,
        field: "predecessorTaskEventHash"
    )
    let bootstrap = try decodeRequest(
        BootstrapRecordIdentity.self,
        from: readGenericPassword(locator: FixedLocator.bootstrapRecord)
    )
    guard document.installationId.lowercased()
            == bootstrap.installationId.lowercased() else {
        throw BrokerFailure.capability("approval installation binding mismatch")
    }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    var expiry = formatter.date(from: document.expiresAt)
    if expiry == nil {
        formatter.formatOptions = [.withInternetDateTime]
        expiry = formatter.date(from: document.expiresAt)
    }
    guard let expiry else {
        throw BrokerFailure.invalidRequest(
            "external-write envelope expiry is invalid"
        )
    }
    let lifetime = expiry.timeIntervalSinceNow
    guard lifetime > 0, lifetime <= 900 else {
        throw BrokerFailure.capability(
            "external-write envelope expiry is invalid"
        )
    }
}

func approvalSignature(_ request: ApprovalSignRequest) throws -> ApprovalSignature {
    guard let envelope = Data(base64Encoded: request.envelopeBase64) else {
        throw BrokerFailure.invalidRequest("approval envelope base64 is invalid")
    }
    try requireApprovalEnvelope(envelope)
    guard !request.summary.trimmingCharacters(
        in: .whitespacesAndNewlines
    ).isEmpty else {
        throw BrokerFailure.invalidRequest(
            "canonical approval display summary is empty"
        )
    }
    try requireProtectedUserPresence(
        reason: "Approve Agent Harness external write: \(request.summary)"
    )
    let summary = Data(request.summary.utf8)
    var signed = Data("agent-harness/approval/v1\0".utf8)
    signed.append(envelope)
    signed.append(0)
    signed.append(summary)
    return ApprovalSignature(
        algorithm: "p256-sha256",
        publicKeyDigest: try publicKeyDigest(locator: FixedLocator.approvalKey),
        envelopeDigest: sha256(envelope),
        summaryDigest: sha256(summary),
        signature: try signPayload(
            locator: FixedLocator.approvalKey, payload: signed
        ).base64EncodedString()
    )
}

func verifyApproval(_ request: ApprovalVerifyRequest) throws -> Bool {
    guard let envelope = Data(base64Encoded: request.envelopeBase64),
          let signature = Data(base64Encoded: request.approval.signature) else {
        return false
    }
    let summary = Data(request.summary.utf8)
    let expectedPublicKeyDigest = try publicKeyDigest(
        locator: FixedLocator.approvalKey
    )
    guard request.approval.algorithm == "p256-sha256",
          request.approval.publicKeyDigest == expectedPublicKeyDigest,
          request.approval.envelopeDigest == sha256(envelope),
          request.approval.summaryDigest == sha256(summary) else {
        return false
    }
    var signed = Data("agent-harness/approval/v1\0".utf8)
    signed.append(envelope)
    signed.append(0)
    signed.append(summary)
    return try verifyPayload(
        locator: FixedLocator.approvalKey,
        payload: signed,
        signature: signature
    )
}

func bootstrap(
    _ request: BootstrapRequest,
    allowExisting: Bool
) throws -> BootstrapManifest {
    guard request.initialAnchorGeneration == 0 else {
        throw BrokerFailure.invalidRequest("initial anchor generation must be zero")
    }
    try requireHexDigest(request.descriptorDigest, field: "descriptorDigest")
    try requireHexDigest(request.finalPlanDigest, field: "finalPlanDigest")
    try requireHexDigest(request.walDigest, field: "walDigest")
    try requireHexDigest(
        request.initialAnchorCommitment, field: "initialAnchorCommitment"
    )
    let attestation = try brokerAttestation()
    let approvalSummary = try validateBootstrapPlan(
        request,
        attestation: attestation
    )
    try requireProtectedUserPresence(
        reason: "Approve Agent Harness bootstrap \(sha256(approvalSummary))"
    )
    let installationId = request.installationId.uuidString.lowercased()
    let approvalMarker = [
        "approval-key",
        installationId,
        request.descriptorDigest,
        request.walDigest,
    ].joined(separator: ":")
    let receiptMarker = [
        "receipt-key",
        installationId,
        request.descriptorDigest,
        request.walDigest,
        attestation.codeIdentity,
    ].joined(separator: ":")
    let integrityMarker = [
        "integrity-key",
        installationId,
        request.descriptorDigest,
        request.walDigest,
        attestation.codeIdentity,
    ].joined(separator: ":")

    return try withAuthorityLock {
        if !allowExisting {
            let approvalExists = try existingSecureEnclaveKey(
                locator: FixedLocator.approvalKey,
                marker: approvalMarker
            ) != nil
            let receiptExists = try existingSecureEnclaveKey(
                locator: FixedLocator.receiptKey,
                marker: receiptMarker
            ) != nil
            let integrityExists = try existingIntegrityKey(
                marker: integrityMarker
            ) != nil
            let anchorExists = try genericPasswordExists(
                locator: FixedLocator.anchor
            )
            let recordExists = try genericPasswordExists(
                locator: FixedLocator.bootstrapRecord
            )
            guard !approvalExists, !receiptExists, !integrityExists,
                  !anchorExists, !recordExists else {
                throw BrokerFailure.capability(
                    "authority bootstrap fixed locators are not absent"
                )
            }
        }

        let approval = try ensureSecureEnclaveKey(
            locator: FixedLocator.approvalKey,
            marker: approvalMarker,
            protectedUserPresence: true
        )
        let receipt = try ensureSecureEnclaveKey(
            locator: FixedLocator.receiptKey,
            marker: receiptMarker,
            protectedUserPresence: false
        )
        let integrity = try ensureIntegrityKey(marker: integrityMarker)
        let anchorPayload = try JSONSerialization.data(
            withJSONObject: [
                "installation_id": installationId,
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
        try ensureGenericPassword(
            locator: FixedLocator.anchor,
            payload: anchorPayload,
            accessibility: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        )
        let recordPayload = try JSONSerialization.data(
            withJSONObject: [
                "installation_id": installationId,
                "creator_id": request.creatorId,
                "broker_code_identity": attestation.codeIdentity,
                "broker_content_digest": attestation.contentDigest,
                "descriptor_digest": request.descriptorDigest,
                "final_plan_digest": request.finalPlanDigest,
                "wal_digest": request.walDigest,
                "approval_key_locator": FixedLocator.approvalKey,
                "approval_public_key_digest": approval.publicDigest,
                "anchor_locator": FixedLocator.anchor,
                "receipt_key_locator": FixedLocator.receiptKey,
                "receipt_public_key_digest": receipt.publicDigest,
                "integrity_key_id": "native-integrity:\(installationId)",
                "integrity_key_locator": FixedLocator.integrityKey,
                "integrity_persistent_reference":
                    integrity.persistentReference,
            ],
            options: [.sortedKeys]
        )
        try ensureGenericPassword(
            locator: FixedLocator.bootstrapRecord,
            payload: recordPayload,
            accessibility: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        )

        guard let approvalReadback = try existingSecureEnclaveKey(
                  locator: FixedLocator.approvalKey,
                  marker: approvalMarker
              ),
              approvalReadback.publicDigest == approval.publicDigest,
              approvalReadback.persistentReference
                  == approval.persistentReference,
              let receiptReadback = try existingSecureEnclaveKey(
                  locator: FixedLocator.receiptKey,
                  marker: receiptMarker
              ),
              receiptReadback.publicDigest == receipt.publicDigest,
              receiptReadback.persistentReference
                  == receipt.persistentReference,
              let integrityReadback = try existingIntegrityKey(
                  marker: integrityMarker
              ),
              integrityReadback.key == integrity.key,
              integrityReadback.persistentReference
                  == integrity.persistentReference,
              try readGenericPassword(locator: FixedLocator.anchor)
                  == anchorPayload,
              try readGenericPassword(locator: FixedLocator.bootstrapRecord)
                  == recordPayload else {
            throw BrokerFailure.capability(
                "authority bootstrap exact readback failed"
            )
        }
        let phaseProbe = Data(
            "agent-harness/integrity-key-readback/v1\0".utf8
        )
        let phaseMAC = HMAC<SHA256>.authenticationCode(
            for: phaseProbe,
            using: SymmetricKey(data: integrityReadback.key)
        )
        guard HMAC<SHA256>.isValidAuthenticationCode(
            phaseMAC,
            authenticating: phaseProbe,
            using: SymmetricKey(data: integrityReadback.key)
        ) else {
            throw BrokerFailure.capability(
                "integrity key phase MAC readback failed"
            )
        }

        let unsigned = BootstrapManifest(
            schema: "agent-harness/authority-manifest",
            schemaVersion: 1,
            createdAt: request.createdAt,
            installationId: installationId,
            brokerCodeIdentity: attestation.codeIdentity,
            brokerContentDigest: attestation.contentDigest,
            approvalPublicKeyDigest: approval.publicDigest,
            approvalPersistentReference: approval.persistentReference,
            anchorBackendId: "native-keychain-anchor-v1",
            anchorNamespace: request.anchorNamespace,
            receiptKeyId: "broker-receipt:\(installationId)",
            receiptPublicKeyDigest: receipt.publicDigest,
            receiptPersistentReference: receipt.persistentReference,
            integrityKeyId: "native-integrity:\(installationId)",
            integrityKeyLocator: FixedLocator.integrityKey,
            integrityPersistentReference:
                integrity.persistentReference,
            terminalPinLocator: FixedLocator.terminalPin,
            terminalPinAttributes: TerminalPinAttributes(
                addOnly: true,
                containsKeyMaterial: false,
                synchronizable: false,
                accessibility: "AfterFirstUnlockThisDeviceOnly"
            ),
            capabilityState: [
                "protected-user-presence-approval",
                "installation-anchor-cas",
                "broker-signed-receipts",
                "retirement-terminal-pin-add",
            ],
            bootstrapDigest: request.descriptorDigest,
            pendingPlanCommitment: request.finalPlanDigest,
            brokerSignature: nil
        )
        let payload = try canonicalJSON(unsigned)
        let signature = try signPayload(
            locator: FixedLocator.receiptKey,
            payload: payload
        )
        guard try verifyPayload(
            locator: FixedLocator.receiptKey,
            payload: payload,
            signature: signature
        ) else {
            throw BrokerFailure.capability(
                "authority bootstrap manifest signature readback failed"
            )
        }
        return BootstrapManifest(
            schema: unsigned.schema,
            schemaVersion: unsigned.schemaVersion,
            createdAt: unsigned.createdAt,
            installationId: unsigned.installationId,
            brokerCodeIdentity: unsigned.brokerCodeIdentity,
            brokerContentDigest: unsigned.brokerContentDigest,
            approvalPublicKeyDigest: unsigned.approvalPublicKeyDigest,
            approvalPersistentReference: unsigned.approvalPersistentReference,
            anchorBackendId: unsigned.anchorBackendId,
            anchorNamespace: unsigned.anchorNamespace,
            receiptKeyId: unsigned.receiptKeyId,
            receiptPublicKeyDigest: unsigned.receiptPublicKeyDigest,
            receiptPersistentReference: unsigned.receiptPersistentReference,
            integrityKeyId: unsigned.integrityKeyId,
            integrityKeyLocator: unsigned.integrityKeyLocator,
            integrityPersistentReference:
                unsigned.integrityPersistentReference,
            terminalPinLocator: unsigned.terminalPinLocator,
            terminalPinAttributes: unsigned.terminalPinAttributes,
            capabilityState: unsigned.capabilityState,
            bootstrapDigest: unsigned.bootstrapDigest,
            pendingPlanCommitment: unsigned.pendingPlanCommitment,
            brokerSignature: signature.base64EncodedString()
        )
    }
}

func addRetirementPin(_ request: RetirementPinRequest) throws {
    try requireHexDigest(request.attestationDigest, field: "attestationDigest")
    try requireHexDigest(
        request.receiptPublicKeyDigest, field: "receiptPublicKeyDigest"
    )
    try requireHexDigest(
        request.helperFinalizerDigest, field: "helperFinalizerDigest"
    )
    guard let encodedSignature = request.brokerSignature,
          let signature = Data(base64Encoded: encodedSignature) else {
        throw BrokerFailure.capability(
            "authenticated retirement capability required"
        )
    }
    let unsigned = RetirementPinRequest(
        installationId: request.installationId,
        authorityEra: request.authorityEra,
        attestationDigest: request.attestationDigest,
        receiptPublicKeyDigest: request.receiptPublicKeyDigest,
        helperObjectIdentity: request.helperObjectIdentity,
        helperFinalizerDigest: request.helperFinalizerDigest,
        brokerSignature: nil
    )
    guard try verifyPayload(
        locator: FixedLocator.receiptKey,
        payload: canonicalJSON(unsigned),
        signature: signature
    ) else {
        throw BrokerFailure.capability(
            "authenticated retirement capability required"
        )
    }
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
        FixedLocator.integrityKey,
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
    let manifest = BootstrapManifest(
        schema: "agent-harness/authority-manifest",
        schemaVersion: 1,
        createdAt: "2000-01-01T00:00:00Z",
        installationId: "00000000-0000-4000-8000-000000000000",
        brokerCodeIdentity: "self-test",
        brokerContentDigest: String(repeating: "0", count: 64),
        approvalPublicKeyDigest: String(repeating: "1", count: 64),
        approvalPersistentReference: "opaque:self-test-approval",
        anchorBackendId: "native-keychain-anchor-v1",
        anchorNamespace: "self-test",
        receiptKeyId: "broker-receipt:self-test",
        receiptPublicKeyDigest: String(repeating: "2", count: 64),
        receiptPersistentReference: "opaque:self-test-receipt",
        integrityKeyId: "native-integrity:self-test",
        integrityKeyLocator: FixedLocator.integrityKey,
        integrityPersistentReference: "opaque:self-test-integrity",
        terminalPinLocator: FixedLocator.terminalPin,
        terminalPinAttributes: TerminalPinAttributes(
            addOnly: true,
            containsKeyMaterial: false,
            synchronizable: false,
            accessibility: "AfterFirstUnlockThisDeviceOnly"
        ),
        capabilityState: [
            "protected-user-presence-approval",
            "installation-anchor-cas",
            "broker-signed-receipts",
            "retirement-terminal-pin-add",
        ],
        bootstrapDigest: String(repeating: "3", count: 64),
        pendingPlanCommitment: String(repeating: "4", count: 64),
        brokerSignature: nil
    )
    guard let manifestObject = try JSONSerialization.jsonObject(
              with: canonicalJSON(manifest)
          ) as? [String: Any],
          manifestObject["schema"] as? String
              == "agent-harness/authority-manifest",
          manifestObject["schema_version"] as? Int == 1,
          manifestObject["terminal_pin_locator"] as? String
              == FixedLocator.terminalPin,
          manifestObject["integrity_key_locator"] as? String
              == FixedLocator.integrityKey,
          manifestObject["broker_signature"] == nil else {
        throw BrokerFailure.capability(
            "authority bootstrap manifest contract is invalid"
        )
    }
    let phaseKey = SymmetricKey(data: Data(repeating: 7, count: 32))
    let phasePayload = Data("self-test-phase".utf8)
    let phaseMAC = HMAC<SHA256>.authenticationCode(
        for: phasePayload,
        using: phaseKey
    )
    let rawBootstrapRejected: Bool
    do {
        _ = try authenticatedBootstrapRequest(
            from: Data("{}".utf8),
            capability: { Data(repeating: 9, count: 32) }
        )
        rawBootstrapRejected = false
    } catch {
        rawBootstrapRejected = true
    }
    let evidence: [String: Any] = [
        "ok": true,
        "raw_bootstrap_rejected": rawBootstrapRejected,
        "control_authority_provisioned":
            manifestObject["integrity_key_locator"] as? String
                == FixedLocator.integrityKey,
        "control_locator": FixedLocator.integrityKey,
        "anchor_locator": FixedLocator.anchor,
        "phase_mac_round_trip":
            HMAC<SHA256>.isValidAuthenticationCode(
                phaseMAC,
                authenticating: phasePayload,
                using: phaseKey
            ),
        "manifest_contract_valid": true,
        "keychain_mutated": false,
        "user_presence_requested": false,
    ]
    FileHandle.standardOutput.write(try canonicalJSONObject(evidence))
    FileHandle.standardOutput.write(Data([0x0a]))
}

do {
    let arguments = Array(CommandLine.arguments.dropFirst())
    guard arguments.count == 1 else {
        throw BrokerFailure.invalidRequest(
            "usage: macos-broker --attest|--self-test|bootstrap|bootstrap-recover|health|anchor-read|anchor-compare-and-advance|receipt-verify|approval-sign|approval-verify|retirement-pin"
        )
    }
    switch arguments[0] {
    case "--attest":
        FileHandle.standardOutput.write(try canonicalJSON(brokerAttestation()))
        FileHandle.standardOutput.write(Data([0x0a]))
    case "--self-test":
        try selfTest()
    case "bootstrap":
        let request = try authenticatedBootstrapRequest(
            from: readBoundedStdin()
        )
        let manifest = try bootstrap(request, allowExisting: false)
        FileHandle.standardOutput.write(try canonicalJSON(manifest))
        FileHandle.standardOutput.write(Data([0x0a]))
    case "bootstrap-recover":
        let request = try authenticatedBootstrapRequest(
            from: readBoundedStdin()
        )
        let manifest = try bootstrap(request, allowExisting: true)
        FileHandle.standardOutput.write(try canonicalJSON(manifest))
        FileHandle.standardOutput.write(Data([0x0a]))
    case "health":
        let attestation = try brokerAttestation()
        let context = LAContext()
        var evaluationError: NSError?
        let response = HealthResponse(
            healthy: true,
            codeIdentity: attestation.codeIdentity,
            contentDigest: attestation.contentDigest,
            approvalPublicKeyDigest: try publicKeyDigest(
                locator: FixedLocator.approvalKey
            ),
            userPresenceAvailable: context.canEvaluatePolicy(
                .deviceOwnerAuthentication, error: &evaluationError
            )
        )
        FileHandle.standardOutput.write(try canonicalJSON(response))
        FileHandle.standardOutput.write(Data([0x0a]))
    case "anchor-read":
        let request = try decodeRequest(
            AnchorReadRequest.self, from: readBoundedStdin()
        )
        FileHandle.standardOutput.write(
            try canonicalJSON(anchorState(expectedNamespace: request.namespace))
        )
        FileHandle.standardOutput.write(Data([0x0a]))
    case "anchor-compare-and-advance":
        let request = try decodeRequest(
            AnchorCASRequest.self, from: readBoundedStdin()
        )
        FileHandle.standardOutput.write(
            try canonicalJSON(compareAndAdvance(request))
        )
        FileHandle.standardOutput.write(Data([0x0a]))
    case "receipt-verify":
        let request = try decodeRequest(
            ReceiptVerifyRequest.self, from: readBoundedStdin()
        )
        guard let payload = Data(base64Encoded: request.payloadBase64),
              let signature = Data(base64Encoded: request.signature) else {
            throw BrokerFailure.invalidRequest(
                "receipt verification base64 is invalid"
            )
        }
        FileHandle.standardOutput.write(
            try canonicalJSON(
                BoolResponse(
                    valid: try verifyPayload(
                        locator: FixedLocator.receiptKey,
                        payload: payload,
                        signature: signature
                    )
                )
            )
        )
        FileHandle.standardOutput.write(Data([0x0a]))
    case "approval-sign":
        let request = try decodeRequest(
            ApprovalSignRequest.self, from: readBoundedStdin()
        )
        FileHandle.standardOutput.write(
            try canonicalJSON(approvalSignature(request))
        )
        FileHandle.standardOutput.write(Data([0x0a]))
    case "approval-verify":
        let request = try decodeRequest(
            ApprovalVerifyRequest.self, from: readBoundedStdin()
        )
        FileHandle.standardOutput.write(
            try canonicalJSON(BoolResponse(valid: try verifyApproval(request)))
        )
        FileHandle.standardOutput.write(Data([0x0a]))
    case "retirement-pin":
        let request = try decodeRequest(
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
