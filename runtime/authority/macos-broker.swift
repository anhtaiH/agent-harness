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
    let launcherCodeIdentity: String
    let launcherContentDigest: String
    let walDigest: String
    let anchorNamespace: String
    let initialAnchorGeneration: Int
    let initialAnchorCommitment: String
}

struct ControllerAuthorizationBody: Codable, Equatable {
    let schema: String
    let schemaVersion: Int
    let operation: String
    let recoveryPolicy: String
    let controllerNonce: String
    let requestDigest: String
    let setupBodyDigest: String
    let descriptorDigest: String
    let finalPlanDigest: String
    let walDigest: String
    let controllerPublicKeyDigest: String
    let verifierCodeDirectoryHash: String
    let brokerCodeDirectoryHash: String
    let providerKind: String
    let buildProfile: String
}

struct ControllerAuthorization: Codable {
    let schema: String
    let schemaVersion: Int
    let operation: String
    let recoveryPolicy: String
    let controllerNonce: String
    let requestDigest: String
    let setupBodyDigest: String
    let descriptorDigest: String
    let finalPlanDigest: String
    let walDigest: String
    let controllerPublicKeyDigest: String
    let verifierCodeDirectoryHash: String
    let brokerCodeDirectoryHash: String
    let providerKind: String
    let buildProfile: String
    let signature: String

    var body: ControllerAuthorizationBody {
        ControllerAuthorizationBody(
            schema: schema,
            schemaVersion: schemaVersion,
            operation: operation,
            recoveryPolicy: recoveryPolicy,
            controllerNonce: controllerNonce,
            requestDigest: requestDigest,
            setupBodyDigest: setupBodyDigest,
            descriptorDigest: descriptorDigest,
            finalPlanDigest: finalPlanDigest,
            walDigest: walDigest,
            controllerPublicKeyDigest: controllerPublicKeyDigest,
            verifierCodeDirectoryHash: verifierCodeDirectoryHash,
            brokerCodeDirectoryHash: brokerCodeDirectoryHash,
            providerKind: providerKind,
            buildProfile: buildProfile
        )
    }
}

struct ControllerRecoveryRelease: Codable, Equatable {
    let schema: String
    let schemaVersion: Int
    let operation: String
    let recoveryPolicy: String
    let requestDigest: String
    let setupBodyDigest: String
    let descriptorDigest: String
    let finalPlanDigest: String
    let walDigest: String
    let controllerPublicKeyDigest: String
    let verifierCodeDirectoryHash: String
    let brokerCodeDirectoryHash: String
    let providerKind: String
    let buildProfile: String
}

struct BrokerSessionRequest: Codable {
    let protocolVersion: Int
    let operation: String
    let recovery: Bool
    let verifierNonce: String
    let requestDigest: String
    let finalPlanDigest: String
    let request: BootstrapRequest
    let controllerAuthorization: ControllerAuthorization?
    let testResponseMutation: String?
}

struct BrokerSessionCommit: Codable {
    let protocolVersion: Int
    let operation: String
    let recovery: Bool
    let verifierNonce: String
    let brokerNonce: String
    let requestDigest: String
    let finalPlanDigest: String
}

struct BrokerSessionResponse: Codable {
    let protocolVersion: Int
    let operation: String
    let recovery: Bool
    let verifierNonce: String
    let brokerNonce: String
    let requestDigest: String
    let finalPlanDigest: String
    let manifest: BootstrapManifest?
    let signature: String
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

struct BootstrapManifest: Codable {
    let schema: String
    let schemaVersion: Int
    let createdAt: String
    let installationId: String
    let launcherCodeIdentity: String
    let launcherContentDigest: String
    let nativeBrokerCodeIdentity: String
    let nativeBrokerContentDigest: String
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
    let authorityProvider: String
    let verifierMode: String
    let controllerPublicKeyDigest: String
    let launcherCodeIdentity: String
    let launcherCodeDirectoryHash: String
    let launcherContentDigest: String
    let nativeBrokerCodeIdentity: String
    let nativeBrokerCodeDirectoryHash: String
    let nativeBrokerContentDigest: String
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

func readBounded(_ handle: FileHandle) throws -> Data {
    var result = Data()
    while true {
        let chunk = handle.readData(ofLength: 16_384)
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

func readBoundedStdin() throws -> Data {
    try readBounded(FileHandle.standardInput)
}

func readBootstrapVerifierRequest() throws -> Data {
    guard
        let encoded = ProcessInfo.processInfo.environment[
            "AGENT_HARNESS_BOOTSTRAP_REQUEST_FD"
        ],
        let descriptor = Int32(encoded),
        descriptor > STDERR_FILENO
    else {
        throw BrokerFailure.capability(
            "private native bootstrap request channel required"
        )
    }
    defer { close(descriptor) }
    var metadata = stat()
    guard fstat(descriptor, &metadata) == 0,
          (metadata.st_mode & S_IFMT) == S_IFREG,
          metadata.st_size > 0,
          metadata.st_size <= maximumRequestBytes,
          lseek(descriptor, 0, SEEK_SET) == 0 else {
        throw BrokerFailure.capability(
            "bounded regular native bootstrap request required"
        )
    }
    let data = try readBounded(
        FileHandle(fileDescriptor: descriptor, closeOnDealloc: false)
    )
    guard data.count == metadata.st_size,
          let original = try JSONSerialization.jsonObject(with: data)
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
        "launcher_code_identity",
        "launcher_content_digest",
        "wal_digest",
        "anchor_namespace",
        "initial_anchor_generation",
        "initial_anchor_commitment",
    ]
    guard Set(original.keys) == expectedFields else {
        throw BrokerFailure.invalidRequest(
            "bootstrap request fields mismatch"
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
    return data
}

func readControllerRelease() throws
    -> (data: Data, descriptor: Int32)
{
    guard
        let encoded = ProcessInfo.processInfo.environment[
            "AGENT_HARNESS_BOOTSTRAP_CONTROLLER_FD"
        ],
        let descriptor = Int32(encoded),
        descriptor > STDERR_FILENO
    else {
        throw BrokerFailure.capability(
            "private bootstrap controller channel required"
        )
    }
    do {
        try configureSessionTimeout(descriptor)
        _ = fcntl(descriptor, F_SETFD, FD_CLOEXEC)
        let data = try readSessionFrame(from: descriptor)
        return (data, descriptor)
    } catch {
        close(descriptor)
        throw error
    }
}

func requireControllerSessionAlive(_ descriptor: Int32) throws {
    var byte: UInt8 = 0
    let result = Darwin.recv(
        descriptor,
        &byte,
        1,
        MSG_PEEK | MSG_DONTWAIT
    )
    if result == 0 {
        throw BrokerFailure.capability(
            "bootstrap controller session is closed"
        )
    }
    if result < 0 && errno != EAGAIN && errno != EWOULDBLOCK {
        throw BrokerFailure.capability(
            "bootstrap controller session is unavailable"
        )
    }
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

func signedMetadataString(_ key: String) throws -> String {
    guard
        let value = Bundle.main.object(forInfoDictionaryKey: key)
            as? String,
        !value.isEmpty
    else {
        throw BrokerFailure.capability(
            "signed authority metadata \(key) is unavailable"
        )
    }
    return value
}

func authorityProvider() throws -> String {
    let provider = try signedMetadataString("AgentHarnessProvider")
#if AGENT_HARNESS_SECURITY_PROVIDER
    guard provider == "security" else {
        throw BrokerFailure.capability(
            "signed authority provider does not match compiled provider"
        )
    }
    return "security"
#elseif AGENT_HARNESS_SIGNED_MEMORY_PROVIDER
    guard provider == "signed-memory" else {
        throw BrokerFailure.capability(
            "signed authority provider does not match compiled provider"
        )
    }
    return "signed-memory"
#else
    throw BrokerFailure.capability(
        "authority provider is not compiled"
    )
#endif
}

func controllerPublicKeyData() throws -> Data {
    guard
        let data = Data(
            base64Encoded: try signedMetadataString(
                "AgentHarnessControllerPublicKey"
            )
        ),
        !data.isEmpty
    else {
        throw BrokerFailure.capability(
            "signed controller public key is invalid"
        )
    }
    return data
}

func verifierTestModeEnabled() -> Bool {
    (try? verifierMode()) == "test"
}

func verifierMode() throws -> String {
    let mode = try signedMetadataString("AgentHarnessVerifierMode")
    guard mode == "production" || mode == "test" else {
        throw BrokerFailure.capability(
            "signed authority verifier mode is invalid"
        )
    }
    return mode
}

func signedMemoryStatePath() throws -> String {
    let path = try signedMetadataString("AgentHarnessStatePath")
    guard path.hasPrefix("/") else {
        throw BrokerFailure.capability(
            "signed authority state path must be absolute"
        )
    }
    return path
}

func withSignedMemoryState<T>(
    _ operation: (inout [String: Any]) throws -> T
) throws -> T {
    guard try authorityProvider() == "signed-memory" else {
        throw BrokerFailure.capability(
            "signed-memory provider is unavailable"
        )
    }
    let statePath = try signedMemoryStatePath()
    let lockPath = statePath + ".lock"
    let lockDescriptor = open(
        lockPath,
        O_CREAT | O_RDWR | O_NOFOLLOW,
        S_IRUSR | S_IWUSR
    )
    guard lockDescriptor >= 0,
          flock(lockDescriptor, LOCK_EX) == 0 else {
        if lockDescriptor >= 0 { close(lockDescriptor) }
        throw BrokerFailure.capability(
            "signed-memory state lock is unavailable"
        )
    }
    defer {
        flock(lockDescriptor, LOCK_UN)
        close(lockDescriptor)
    }
    var state: [String: Any] = [
        "provider": "signed-memory",
        "dispatch_count": 0,
        "reservation_count": 0,
        "mutation_count": 0,
        "accepted_response_count": 0,
        "keychain_mutated": false,
        "user_presence_requested": false,
    ]
    if FileManager.default.fileExists(atPath: statePath) {
        let data = try Data(contentsOf: URL(fileURLWithPath: statePath))
        guard let existing = try JSONSerialization.jsonObject(with: data)
                as? [String: Any] else {
            throw BrokerFailure.capability(
                "signed-memory state is malformed"
            )
        }
        state.merge(existing) { _, current in current }
    }
    let result = try operation(&state)
    let encoded = try canonicalJSONObject(state)
    try encoded.write(
        to: URL(fileURLWithPath: statePath),
        options: .atomic
    )
    return result
}

func incrementSignedMemoryState(_ field: String) throws {
    try withSignedMemoryState { state in
        state[field] = (state[field] as? Int ?? 0) + 1
    }
}

func reserveSignedMemoryDispatch(
    _ session: BrokerSessionRequest,
    brokerNonce: String
) throws {
    try withSignedMemoryState { state in
        guard (state["dispatch_count"] as? Int ?? 0) == 0 else {
            throw BrokerFailure.capability(
                "signed-memory bootstrap is already reserved"
            )
        }
        state["dispatch_count"] = 1
        state["reservation_count"] =
            (state["reservation_count"] as? Int ?? 0) + 1
        state["reserved_operation"] = session.operation
        state["reserved_recovery"] = session.recovery
        state["reserved_verifier_nonce"] = session.verifierNonce
        state["reserved_broker_nonce"] = brokerNonce
        state["reserved_request_digest"] = session.requestDigest
        state["reserved_final_plan_digest"] =
            session.finalPlanDigest
        if let authorization = session.controllerAuthorization {
            let authorizationData = try canonicalJSON(authorization)
            state["reserved_controller_public_key_digest"] =
                authorization.controllerPublicKeyDigest
            state["reserved_controller_authorization_base64"] =
                authorizationData.base64EncodedString()
            state["reserved_controller_authorization_digest"] =
                sha256(authorizationData)
            state["reserved_controller_signature_digest"] =
                sha256(Data(authorization.signature.utf8))
            state["reservation_state"] = "RESERVED"
        }
    }
}

func signedMemoryReservedControllerAuthorization(
    request: BootstrapRequest
) throws
    -> ControllerAuthorization
{
    try withSignedMemoryState { state in
        guard (state["dispatch_count"] as? Int ?? 0) == 1,
              (state["reservation_count"] as? Int ?? 0) == 1,
              state["reserved_operation"] as? String == "bootstrap",
              state["reserved_recovery"] as? Bool == false,
              state["reserved_request_digest"] as? String
                == sha256(try canonicalJSON(request)),
              state["reserved_final_plan_digest"] as? String
                == request.finalPlanDigest,
              state["reservation_state"] as? String == "RESERVED",
              (state["mutation_count"] as? Int ?? 0) == 0,
              let encoded =
                state["reserved_controller_authorization_base64"] as? String,
              let authorizationData = Data(base64Encoded: encoded) else {
            throw BrokerFailure.capability(
                "exact signed-memory recovery reservation is absent"
            )
        }
        let authorization = try decodeRequest(
            ControllerAuthorization.self,
            from: authorizationData
        )
        guard try canonicalJSON(authorization) == authorizationData,
              state["reserved_controller_public_key_digest"] as? String
                == authorization.controllerPublicKeyDigest,
              state["reserved_verifier_nonce"] as? String
                == authorization.controllerNonce,
              state["reserved_controller_authorization_digest"] as? String
                == sha256(authorizationData),
              state["reserved_controller_signature_digest"] as? String
                == sha256(Data(authorization.signature.utf8)) else {
            throw BrokerFailure.capability(
                "signed-memory recovery reservation binding mismatch"
            )
        }
        return authorization
    }
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

func staticSecurityCode(_ code: SecCode) throws -> SecStaticCode {
    var staticCode: SecStaticCode?
    let status = SecCodeCopyStaticCode(code, [], &staticCode)
    guard status == errSecSuccess, let staticCode else {
        throw BrokerFailure.security("derive native static code", status)
    }
    return staticCode
}

func liveSecurityCode(forPID pid: pid_t) throws -> SecCode {
    let attributes = [
        kSecGuestAttributePid as String: NSNumber(value: pid)
    ] as CFDictionary
    var code: SecCode?
    let status = SecCodeCopyGuestWithAttributes(
        nil,
        attributes,
        [],
        &code
    )
    guard status == errSecSuccess, let code else {
        throw BrokerFailure.security("derive live verifier code", status)
    }
    return code
}

func localPeerIdentity(
    socket descriptor: Int32
) throws -> (pid: pid_t, credential: xucred) {
    var pid: pid_t = 0
    var pidLength = socklen_t(MemoryLayout<pid_t>.size)
    let pidStatus = Darwin.getsockopt(
        descriptor,
        SOL_LOCAL,
        LOCAL_PEERPID,
        &pid,
        &pidLength
    )
    guard pidStatus == 0,
          pidLength == socklen_t(MemoryLayout<pid_t>.size),
          pid > 0 else {
        throw BrokerFailure.capability(
            "derive native verifier peer PID: errno \(errno)"
        )
    }
    var credential = xucred()
    var credentialLength = socklen_t(MemoryLayout<xucred>.size)
    let credentialStatus = Darwin.getsockopt(
        descriptor,
        SOL_LOCAL,
        LOCAL_PEERCRED,
        &credential,
        &credentialLength
    )
    guard credentialStatus == 0,
          credentialLength == socklen_t(MemoryLayout<xucred>.size),
          credential.cr_version == XUCRED_VERSION else {
        throw BrokerFailure.capability(
            "derive native verifier peer credentials: errno \(errno)"
        )
    }
    return (pid, credential)
}

struct MeasuredCodeIdentity {
    let requirement: String
    let codeDirectoryHash: String
    let contentDigest: String

    var descriptorIdentity: String {
        "designated:\(requirement)"
    }
}

func requirementString(_ staticCode: SecStaticCode) throws -> String {
    var requirement: SecRequirement?
    var status = SecCodeCopyDesignatedRequirement(
        staticCode,
        [],
        &requirement
    )
    guard status == errSecSuccess, let requirement else {
        throw BrokerFailure.security(
            "derive designated requirement",
            status
        )
    }
    var text: CFString?
    status = SecRequirementCopyString(requirement, [], &text)
    guard status == errSecSuccess, let text else {
        throw BrokerFailure.security(
            "serialize designated requirement",
            status
        )
    }
    return text as String
}

func codeDirectoryHash(_ staticCode: SecStaticCode) throws -> String {
    var information: CFDictionary?
    let status = SecCodeCopySigningInformation(
        staticCode,
        SecCSFlags(rawValue: kSecCSSigningInformation),
        &information
    )
    guard status == errSecSuccess,
          let dictionary = information as? [CFString: Any],
          let unique = dictionary[kSecCodeInfoUnique] as? Data,
          !unique.isEmpty else {
        throw BrokerFailure.security(
            "derive code-directory hash",
            status
        )
    }
    return unique.map { String(format: "%02x", $0) }.joined()
}

func measuredCodeIdentity(at url: URL) throws -> MeasuredCodeIdentity {
    let canonical = url.resolvingSymlinksInPath().standardizedFileURL
    var staticCode: SecStaticCode?
    let status = SecStaticCodeCreateWithPath(
        canonical as CFURL,
        [],
        &staticCode
    )
    guard status == errSecSuccess, let staticCode else {
        throw BrokerFailure.security(
            "open signed authority role",
            status
        )
    }
    let validity = SecStaticCodeCheckValidity(staticCode, [], nil)
    guard validity == errSecSuccess else {
        throw BrokerFailure.security(
            "validate signed authority role",
            validity
        )
    }
    return MeasuredCodeIdentity(
        requirement: try requirementString(staticCode),
        codeDirectoryHash: try codeDirectoryHash(staticCode),
        contentDigest: sha256(try Data(contentsOf: canonical))
    )
}

func measuredLiveCodeIdentity(
    _ code: SecCode
) throws -> (requirement: String, codeDirectoryHash: String) {
    let staticCode = try staticSecurityCode(code)
    return (
        requirement: try requirementString(staticCode),
        codeDirectoryHash: try codeDirectoryHash(staticCode)
    )
}

func requirement(from text: String) throws -> SecRequirement {
    var requirement: SecRequirement?
    let status = SecRequirementCreateWithString(
        text as CFString,
        [],
        &requirement
    )
    guard status == errSecSuccess, let requirement else {
        throw BrokerFailure.security(
            "parse pinned designated requirement",
            status
        )
    }
    return requirement
}

func authenticateLiveProcess(
    _ pid: pid_t,
    expectedRequirement: String,
    expectedCodeDirectoryHash: String
) throws {
    let code = try liveSecurityCode(forPID: pid)
    let measured = try measuredLiveCodeIdentity(code)
    let validity = SecCodeCheckValidity(
        code,
        [],
        try requirement(from: expectedRequirement)
    )
    guard validity == errSecSuccess,
          measured.requirement == expectedRequirement,
          measured.codeDirectoryHash
            == expectedCodeDirectoryHash.lowercased(),
          kill(pid, 0) == 0 else {
        throw BrokerFailure.capability(
            "live authority process identity mismatch "
                + "(pid \(pid), expected \(expectedRequirement), "
                + "actual \(measured.requirement))"
        )
    }
}

@discardableResult
func authenticateLivePeer(
    socket descriptor: Int32,
    expectedRequirement: String,
    expectedCodeDirectoryHash: String,
    requireParent: Bool
) throws -> pid_t {
    let peer = try localPeerIdentity(socket: descriptor)
    guard peer.credential.cr_uid == geteuid() else {
        throw BrokerFailure.capability(
            "live authority peer effective UID mismatch"
        )
    }
    if requireParent {
        guard peer.pid == getppid() else {
            throw BrokerFailure.capability(
                "live verifier is not broker parent"
            )
        }
    }
    let peerCode = try liveSecurityCode(forPID: peer.pid)
    let measured = try measuredLiveCodeIdentity(peerCode)
    let validity = SecCodeCheckValidity(
        peerCode,
        [],
        try requirement(from: expectedRequirement)
    )
    guard validity == errSecSuccess else {
        throw BrokerFailure.capability(
            "live authority peer designated requirement mismatch "
                + "(pid \(peer.pid), expected \(expectedRequirement), "
                + "actual \(measured.requirement))"
        )
    }
    guard measured.requirement == expectedRequirement,
          measured.codeDirectoryHash
            == expectedCodeDirectoryHash.lowercased() else {
        throw BrokerFailure.capability(
            "live authority peer identity mismatch"
        )
    }
    let rechecked = try localPeerIdentity(socket: descriptor)
    guard rechecked.pid == peer.pid,
          rechecked.credential.cr_uid == peer.credential.cr_uid,
          !requireParent || rechecked.pid == getppid() else {
        throw BrokerFailure.capability(
            "live authority peer changed during authentication"
        )
    }
    return peer.pid
}

func brokerAttestation() throws -> BrokerAttestation {
    let selfIdentity = try measuredCodeIdentity(
        at: currentExecutableURL()
    )
#if AGENT_HARNESS_VERIFIER_ROLE
    let brokerURL = try currentExecutableURL()
        .deletingLastPathComponent()
        .appendingPathComponent("macos-broker-internal")
    let brokerIdentity = try measuredCodeIdentity(at: brokerURL)
    return BrokerAttestation(
        protocolVersion: 1,
        authorityProvider: try authorityProvider(),
        verifierMode: try verifierMode(),
        controllerPublicKeyDigest: sha256(
            try controllerPublicKeyData()
        ),
        launcherCodeIdentity: selfIdentity.descriptorIdentity,
        launcherCodeDirectoryHash: selfIdentity.codeDirectoryHash,
        launcherContentDigest: selfIdentity.contentDigest,
        nativeBrokerCodeIdentity: brokerIdentity.descriptorIdentity,
        nativeBrokerCodeDirectoryHash:
            brokerIdentity.codeDirectoryHash,
        nativeBrokerContentDigest: brokerIdentity.contentDigest
    )
#elseif AGENT_HARNESS_BROKER_ROLE
    return BrokerAttestation(
        protocolVersion: 1,
        authorityProvider: try authorityProvider(),
        verifierMode: try verifierMode(),
        controllerPublicKeyDigest: sha256(
            try controllerPublicKeyData()
        ),
        launcherCodeIdentity: "designated:"
            + (try signedMetadataString(
                "AgentHarnessTrustedVerifierRequirement"
            )),
        launcherCodeDirectoryHash: try signedMetadataString(
            "AgentHarnessTrustedVerifierCodeHash"
        ),
        launcherContentDigest: try signedMetadataString(
            "AgentHarnessTrustedVerifierContentDigest"
        ),
        nativeBrokerCodeIdentity: selfIdentity.descriptorIdentity,
        nativeBrokerCodeDirectoryHash: selfIdentity.codeDirectoryHash,
        nativeBrokerContentDigest: selfIdentity.contentDigest
    )
#else
    throw BrokerFailure.capability("authority role is not compiled")
#endif
}

#if AGENT_HARNESS_VERIFIER_ROLE
do {
    let arguments = Array(CommandLine.arguments.dropFirst())
    guard let command = arguments.first else {
        throw BrokerFailure.invalidRequest(
            "authority verifier command is required"
        )
    }
    switch command {
    case "--attest":
        guard arguments.count == 1 else {
            throw BrokerFailure.invalidRequest(
                "authority attestation accepts no arguments"
            )
        }
        FileHandle.standardOutput.write(
            try canonicalJSON(brokerAttestation())
        )
        FileHandle.standardOutput.write(Data([0x0a]))
    case "--self-test":
        guard arguments.count == 1 else {
            throw BrokerFailure.invalidRequest(
                "authority self-test accepts no arguments"
            )
        }
        try selfTest()
    case "bootstrap":
        try runVerifierBootstrapCommand(command, arguments: arguments)
    case "bootstrap-recover":
        try runVerifierBootstrapCommand(command, arguments: arguments)
    case "receipt-verify":
        guard arguments.count == 1 else {
            throw BrokerFailure.invalidRequest(
                "receipt verification arguments are invalid"
            )
        }
        let request = try decodeRequest(
            ReceiptVerifyRequest.self,
            from: readBoundedStdin()
        )
        guard
            let payload = Data(base64Encoded: request.payloadBase64)
        else {
            throw BrokerFailure.invalidRequest(
                "receipt verification base64 is invalid"
            )
        }
        let valid: Bool
        if try authorityProvider() == "signed-memory" {
            valid = request.signature
                == signedMemoryReceiptSignature(payload)
        } else {
            guard let signature = Data(base64Encoded: request.signature)
            else {
                throw BrokerFailure.invalidRequest(
                    "receipt verification signature is invalid"
                )
            }
            valid = try verifyPayload(
                locator: FixedLocator.receiptKey,
                payload: payload,
                signature: signature
            )
        }
        FileHandle.standardOutput.write(
            try canonicalJSON(BoolResponse(valid: valid))
        )
        FileHandle.standardOutput.write(Data([0x0a]))
    case "health":
        guard arguments.count == 1 else {
            throw BrokerFailure.invalidRequest(
                "authority health arguments are invalid"
            )
        }
        let attestation = try brokerAttestation()
        let signedMemory = try authorityProvider() == "signed-memory"
        let response = HealthResponse(
            healthy: true,
            codeIdentity: attestation.nativeBrokerCodeIdentity,
            contentDigest: attestation.nativeBrokerContentDigest,
            approvalPublicKeyDigest: signedMemory
                ? sha256(Data("signed-memory-approval".utf8))
                : try publicKeyDigest(locator: FixedLocator.approvalKey),
            userPresenceAvailable: !signedMemory
        )
        FileHandle.standardOutput.write(try canonicalJSON(response))
        FileHandle.standardOutput.write(Data([0x0a]))
    case "anchor-read":
        let request = try decodeRequest(
            AnchorReadRequest.self,
            from: readBoundedStdin()
        )
        FileHandle.standardOutput.write(
            try canonicalJSON(
                anchorState(expectedNamespace: request.namespace)
            )
        )
        FileHandle.standardOutput.write(Data([0x0a]))
    case "anchor-compare-and-advance":
        let request = try decodeRequest(
            AnchorCASRequest.self,
            from: readBoundedStdin()
        )
        FileHandle.standardOutput.write(
            try canonicalJSON(compareAndAdvance(request))
        )
        FileHandle.standardOutput.write(Data([0x0a]))
    case "approval-sign":
        let request = try decodeRequest(
            ApprovalSignRequest.self,
            from: readBoundedStdin()
        )
        FileHandle.standardOutput.write(
            try canonicalJSON(approvalSignature(request))
        )
        FileHandle.standardOutput.write(Data([0x0a]))
    case "approval-verify":
        let request = try decodeRequest(
            ApprovalVerifyRequest.self,
            from: readBoundedStdin()
        )
        FileHandle.standardOutput.write(
            try canonicalJSON(
                BoolResponse(valid: try verifyApproval(request))
            )
        )
        FileHandle.standardOutput.write(Data([0x0a]))
    case "retirement-pin":
        let request = try decodeRequest(
            RetirementPinRequest.self,
            from: readBoundedStdin()
        )
        try addRetirementPin(request)
        print("{\"ok\":true}")
    default:
        throw BrokerFailure.invalidRequest(
            "unsupported authority verifier operation"
        )
    }
} catch {
    FileHandle.standardError.write(
        Data("authority verifier: \(error)\n".utf8)
    )
    exit(1)
}
#elseif AGENT_HARNESS_BROKER_ROLE
do {
    let arguments = Array(CommandLine.arguments.dropFirst())
    guard arguments == ["--broker-session"] else {
        throw BrokerFailure.capability(
            "internal authority broker requires authenticated session"
        )
    }
    try runBrokerSession()
} catch {
    FileHandle.standardError.write(
        Data("authority broker: \(error)\n".utf8)
    )
    exit(1)
}
#else
#error("an authority role compile flag is required")
#endif

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
        "launcher_code_identity",
        "launcher_code_directory_hash",
        "launcher_content_digest",
        "native_broker_code_identity",
        "native_broker_code_directory_hash",
        "native_broker_content_digest",
        "authority_provider",
        "verifier_mode",
        "controller_public_key_digest",
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
          !request.launcherCodeIdentity.isEmpty,
          descriptor["launcher_code_identity"] as? String
              == request.launcherCodeIdentity,
          descriptor["launcher_code_directory_hash"] as? String
              == attestation.launcherCodeDirectoryHash,
          descriptor["launcher_content_digest"] as? String
              == request.launcherContentDigest,
          descriptor["native_broker_code_identity"] as? String
              == attestation.nativeBrokerCodeIdentity,
          descriptor["native_broker_code_directory_hash"] as? String
              == attestation.nativeBrokerCodeDirectoryHash,
          descriptor["native_broker_content_digest"] as? String
              == attestation.nativeBrokerContentDigest,
          descriptor["authority_provider"] as? String
              == attestation.authorityProvider,
          descriptor["verifier_mode"] as? String
              == attestation.verifierMode,
          descriptor["controller_public_key_digest"] as? String
              == attestation.controllerPublicKeyDigest,
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
        "launcher_code_identity": request.launcherCodeIdentity,
        "launcher_content_digest": request.launcherContentDigest,
        "native_broker_code_identity": attestation.nativeBrokerCodeIdentity,
        "native_broker_content_digest":
            attestation.nativeBrokerContentDigest,
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
    guard request.brokerCodeIdentity
            == attestation.nativeBrokerCodeIdentity else {
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

func expectedControllerAuthorizationBody(
    request: BootstrapRequest,
    operation: String,
    attestation: BrokerAttestation
) throws -> ControllerAuthorizationBody {
    let planData = try canonicalJSON(request.finalPlan)
    guard
        let plan = try JSONSerialization.jsonObject(with: planData)
            as? [String: Any],
        let setupBodyDigest = plan["setup_body_digest"] as? String
    else {
        throw BrokerFailure.invalidRequest(
            "controller authorization plan binding is malformed"
        )
    }
    return ControllerAuthorizationBody(
        schema: "agent-harness/controller-bootstrap-authorization",
        schemaVersion: 1,
        operation: operation,
        recoveryPolicy: "resume-exact-reservation-only",
        controllerNonce: "",
        requestDigest: sha256(try canonicalJSON(request)),
        setupBodyDigest: setupBodyDigest,
        descriptorDigest: request.descriptorDigest,
        finalPlanDigest: request.finalPlanDigest,
        walDigest: request.walDigest,
        controllerPublicKeyDigest:
            attestation.controllerPublicKeyDigest,
        verifierCodeDirectoryHash:
            attestation.launcherCodeDirectoryHash,
        brokerCodeDirectoryHash:
            attestation.nativeBrokerCodeDirectoryHash,
        providerKind: attestation.authorityProvider == "security"
            ? "macos-security"
            : "signed-memory-test",
        buildProfile: attestation.verifierMode
    )
}

func expectedControllerRecoveryRelease(
    request: BootstrapRequest,
    attestation: BrokerAttestation
) throws -> ControllerRecoveryRelease {
    let authorization = try expectedControllerAuthorizationBody(
        request: request,
        operation: "bootstrap",
        attestation: attestation
    )
    return ControllerRecoveryRelease(
        schema: "agent-harness/controller-bootstrap-recovery",
        schemaVersion: 1,
        operation: "bootstrap-recover",
        recoveryPolicy: authorization.recoveryPolicy,
        requestDigest: authorization.requestDigest,
        setupBodyDigest: authorization.setupBodyDigest,
        descriptorDigest: authorization.descriptorDigest,
        finalPlanDigest: authorization.finalPlanDigest,
        walDigest: authorization.walDigest,
        controllerPublicKeyDigest:
            authorization.controllerPublicKeyDigest,
        verifierCodeDirectoryHash:
            authorization.verifierCodeDirectoryHash,
        brokerCodeDirectoryHash:
            authorization.brokerCodeDirectoryHash,
        providerKind: authorization.providerKind,
        buildProfile: authorization.buildProfile
    )
}

func verifyControllerAuthorization(
    _ authorization: ControllerAuthorization,
    request: BootstrapRequest,
    operation: String,
    attestation: BrokerAttestation
) throws {
    var expected = try expectedControllerAuthorizationBody(
        request: request,
        operation: operation,
        attestation: attestation
    )
    expected = ControllerAuthorizationBody(
        schema: expected.schema,
        schemaVersion: expected.schemaVersion,
        operation: expected.operation,
        recoveryPolicy: expected.recoveryPolicy,
        controllerNonce: authorization.controllerNonce,
        requestDigest: expected.requestDigest,
        setupBodyDigest: expected.setupBodyDigest,
        descriptorDigest: expected.descriptorDigest,
        finalPlanDigest: expected.finalPlanDigest,
        walDigest: expected.walDigest,
        controllerPublicKeyDigest:
            expected.controllerPublicKeyDigest,
        verifierCodeDirectoryHash:
            expected.verifierCodeDirectoryHash,
        brokerCodeDirectoryHash:
            expected.brokerCodeDirectoryHash,
        providerKind: expected.providerKind,
        buildProfile: expected.buildProfile
    )
    guard authorization.body == expected,
          hexadecimalData(authorization.controllerNonce)?.count == 32,
          let signatureData = Data(
            base64Encoded: authorization.signature
          ) else {
        throw BrokerFailure.capability(
            "controller authorization binding mismatch"
        )
    }
    let publicKey = try P256.Signing.PublicKey(
        derRepresentation: controllerPublicKeyData()
    )
    let signature = try P256.Signing.ECDSASignature(
        derRepresentation: signatureData
    )
    guard publicKey.isValidSignature(
        signature,
        for: try canonicalJSON(expected)
    ) else {
        throw BrokerFailure.capability(
            "controller authorization signature mismatch"
        )
    }
}

func verifyBootstrapForMutation(
    _ request: BootstrapRequest
) throws -> BrokerAttestation {
    guard request.initialAnchorGeneration == 0 else {
        throw BrokerFailure.invalidRequest(
            "initial anchor generation must be zero"
        )
    }
    try requireHexDigest(
        request.descriptorDigest,
        field: "descriptorDigest"
    )
    try requireHexDigest(
        request.finalPlanDigest,
        field: "finalPlanDigest"
    )
    try requireHexDigest(
        request.launcherContentDigest,
        field: "launcherContentDigest"
    )
    try requireHexDigest(request.walDigest, field: "walDigest")
    try requireHexDigest(
        request.initialAnchorCommitment,
        field: "initialAnchorCommitment"
    )
    let attestation = try brokerAttestation()
    let approvalSummary = try validateBootstrapPlan(
        request,
        attestation: attestation
    )
    _ = approvalSummary
    return attestation
}

func controllerAuthorizationReservationPayload(
    request: BootstrapRequest,
    authorization: ControllerAuthorization
) throws -> Data {
    let authorizationData = try canonicalJSON(authorization)
    return try JSONSerialization.data(
        withJSONObject: [
            "installation_id":
                request.installationId.uuidString.lowercased(),
            "creator_id": request.creatorId,
            "descriptor_digest": request.descriptorDigest,
            "final_plan_digest": request.finalPlanDigest,
            "wal_digest": request.walDigest,
            "controller_public_key_digest":
                authorization.controllerPublicKeyDigest,
            "controller_authorization_base64":
                authorizationData.base64EncodedString(),
            "controller_authorization_digest":
                sha256(authorizationData),
            "controller_signature_digest":
                sha256(Data(authorization.signature.utf8)),
            "reservation_state": "RESERVED",
        ],
        options: [.sortedKeys]
    )
}

func securityReservedControllerAuthorization(
    request: BootstrapRequest
) throws -> ControllerAuthorization {
    let recordPayload = try readGenericPassword(
        locator: FixedLocator.bootstrapRecord
    )
    guard
        let record = try JSONSerialization.jsonObject(with: recordPayload)
            as? [String: Any],
        let encoded = record["controller_authorization_base64"] as? String,
        let authorizationData = Data(base64Encoded: encoded)
    else {
        throw BrokerFailure.capability(
            "exact controller recovery reservation is absent"
        )
    }
    let authorization = try decodeRequest(
        ControllerAuthorization.self,
        from: authorizationData
    )
    guard try canonicalJSON(authorization) == authorizationData,
          try controllerAuthorizationReservationPayload(
            request: request,
            authorization: authorization
          ) == recordPayload else {
        throw BrokerFailure.capability(
            "controller recovery reservation binding mismatch"
        )
    }
    return authorization
}

func reservedControllerAuthorization(
    request: BootstrapRequest
) throws -> ControllerAuthorization {
    switch try authorityProvider() {
    case "security":
        return try securityReservedControllerAuthorization(request: request)
    case "signed-memory":
        return try signedMemoryReservedControllerAuthorization(
            request: request
        )
    default:
        throw BrokerFailure.capability(
            "authority provider is unsupported"
        )
    }
}

func mutateBootstrap(
    _ request: BootstrapRequest,
    allowExisting: Bool,
    attestation: BrokerAttestation,
    authorization: ControllerAuthorization,
    parentPID: pid_t,
    socket descriptor: Int32
) throws -> BootstrapManifest {
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
        attestation.nativeBrokerCodeIdentity,
    ].joined(separator: ":")
    let integrityMarker = [
        "integrity-key",
        installationId,
        request.descriptorDigest,
        request.walDigest,
        attestation.nativeBrokerCodeIdentity,
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

        let recordPayload = try controllerAuthorizationReservationPayload(
            request: request,
            authorization: authorization
        )
        try ensureGenericPassword(
            locator: FixedLocator.bootstrapRecord,
            payload: recordPayload,
            accessibility: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        )
        guard try readGenericPassword(
            locator: FixedLocator.bootstrapRecord
        ) == recordPayload else {
            throw BrokerFailure.capability(
                "controller authorization reservation readback failed"
            )
        }
        try requireAuthenticatedParentAlive(
            parentPID,
            socket: descriptor
        )
        try requireProtectedUserPresence(
            reason:
                "Approve Agent Harness bootstrap "
                + request.descriptorDigest
        )

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
            launcherCodeIdentity: request.launcherCodeIdentity,
            launcherContentDigest: request.launcherContentDigest,
            nativeBrokerCodeIdentity: attestation.nativeBrokerCodeIdentity,
            nativeBrokerContentDigest:
                attestation.nativeBrokerContentDigest,
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
            launcherCodeIdentity: unsigned.launcherCodeIdentity,
            launcherContentDigest: unsigned.launcherContentDigest,
            nativeBrokerCodeIdentity: unsigned.nativeBrokerCodeIdentity,
            nativeBrokerContentDigest: unsigned.nativeBrokerContentDigest,
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

func unsignedSignedMemoryManifest(
    request: BootstrapRequest,
    attestation: BrokerAttestation
) -> BootstrapManifest {
    let installationId = request.installationId.uuidString.lowercased()
    return BootstrapManifest(
        schema: "agent-harness/authority-manifest",
        schemaVersion: 1,
        createdAt: request.createdAt,
        installationId: installationId,
        launcherCodeIdentity: request.launcherCodeIdentity,
        launcherContentDigest: request.launcherContentDigest,
        nativeBrokerCodeIdentity: attestation.nativeBrokerCodeIdentity,
        nativeBrokerContentDigest:
            attestation.nativeBrokerContentDigest,
        approvalPublicKeyDigest: sha256(
            Data(("approval:" + request.descriptorDigest).utf8)
        ),
        approvalPersistentReference: "opaque:signed-memory-approval",
        anchorBackendId: "native-keychain-anchor-v1",
        anchorNamespace: request.anchorNamespace,
        receiptKeyId: "broker-receipt:\(installationId)",
        receiptPublicKeyDigest: sha256(
            Data(("receipt:" + request.descriptorDigest).utf8)
        ),
        receiptPersistentReference: "opaque:signed-memory-receipt",
        integrityKeyId: "native-integrity:\(installationId)",
        integrityKeyLocator: FixedLocator.integrityKey,
        integrityPersistentReference: "opaque:signed-memory-integrity",
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
}

func manifestSigningPayload(
    _ manifest: BootstrapManifest
) throws -> Data {
    guard var object = try JSONSerialization.jsonObject(
        with: canonicalJSON(manifest)
    ) as? [String: Any] else {
        throw BrokerFailure.capability(
            "signed-memory manifest is malformed"
        )
    }
    object.removeValue(forKey: "broker_signature")
    return try canonicalJSONObject(object)
}

func signedMemoryReceiptSignature(_ payload: Data) -> String {
    sha256(
        Data("agent-harness/signed-memory-receipt/v1\0".utf8)
            + payload
    )
}

func signSignedMemoryManifest(
    _ unsigned: BootstrapManifest
) throws -> BootstrapManifest {
    let signature = signedMemoryReceiptSignature(
        try manifestSigningPayload(unsigned)
    )
    return BootstrapManifest(
        schema: unsigned.schema,
        schemaVersion: unsigned.schemaVersion,
        createdAt: unsigned.createdAt,
        installationId: unsigned.installationId,
        launcherCodeIdentity: unsigned.launcherCodeIdentity,
        launcherContentDigest: unsigned.launcherContentDigest,
        nativeBrokerCodeIdentity: unsigned.nativeBrokerCodeIdentity,
        nativeBrokerContentDigest: unsigned.nativeBrokerContentDigest,
        approvalPublicKeyDigest: unsigned.approvalPublicKeyDigest,
        approvalPersistentReference:
            unsigned.approvalPersistentReference,
        anchorBackendId: unsigned.anchorBackendId,
        anchorNamespace: unsigned.anchorNamespace,
        receiptKeyId: unsigned.receiptKeyId,
        receiptPublicKeyDigest: unsigned.receiptPublicKeyDigest,
        receiptPersistentReference:
            unsigned.receiptPersistentReference,
        integrityKeyId: unsigned.integrityKeyId,
        integrityKeyLocator: unsigned.integrityKeyLocator,
        integrityPersistentReference:
            unsigned.integrityPersistentReference,
        terminalPinLocator: unsigned.terminalPinLocator,
        terminalPinAttributes: unsigned.terminalPinAttributes,
        capabilityState: unsigned.capabilityState,
        bootstrapDigest: unsigned.bootstrapDigest,
        pendingPlanCommitment: unsigned.pendingPlanCommitment,
        brokerSignature: signature
    )
}

func requireAuthenticatedParentAlive(
    _ parentPID: pid_t,
    socket descriptor: Int32
) throws {
    guard getppid() == parentPID,
          kill(parentPID, 0) == 0 else {
        throw BrokerFailure.capability(
            "authenticated verifier parent is no longer alive"
        )
    }
    var byte: UInt8 = 0
    let result = Darwin.recv(
        descriptor,
        &byte,
        1,
        MSG_PEEK | MSG_DONTWAIT
    )
    if result == 0 {
        throw BrokerFailure.capability(
            "authenticated verifier session is closed"
        )
    }
    if result < 0 && errno != EAGAIN && errno != EWOULDBLOCK {
        throw BrokerFailure.capability(
            "authenticated verifier session is unavailable"
        )
    }
}

func mutateBootstrapForProvider(
    _ request: BootstrapRequest,
    allowExisting: Bool,
    attestation: BrokerAttestation,
    authorization: ControllerAuthorization,
    parentPID: pid_t,
    socket descriptor: Int32
) throws -> BootstrapManifest {
    try requireAuthenticatedParentAlive(
        parentPID,
        socket: descriptor
    )
    if try authorityProvider() == "signed-memory" {
        let statePath = try signedMemoryStatePath()
        let stallMarker = URL(fileURLWithPath: statePath)
            .deletingLastPathComponent()
            .appendingPathComponent("stall-before-mutation")
            .path
        if FileManager.default.fileExists(atPath: stallMarker) {
            for _ in 0..<200 {
                try requireAuthenticatedParentAlive(
                    parentPID,
                    socket: descriptor
                )
                usleep(50_000)
            }
        }
        let failureMarker = URL(fileURLWithPath: statePath)
            .deletingLastPathComponent()
            .appendingPathComponent("fail-before-mutation")
            .path
        if FileManager.default.fileExists(atPath: failureMarker) {
            throw BrokerFailure.capability(
                "signed-memory provider failed before mutation"
            )
        }
        try incrementSignedMemoryState("mutation_count")
        return try signSignedMemoryManifest(
            unsignedSignedMemoryManifest(
                request: request,
                attestation: attestation
            )
        )
    }
    return try mutateBootstrap(
        request,
        allowExisting: allowExisting,
        attestation: attestation,
        authorization: authorization,
        parentPID: parentPID,
        socket: descriptor
    )
}

func randomSessionNonce() throws -> String {
    var bytes = [UInt8](repeating: 0, count: 32)
    let status = SecRandomCopyBytes(
        kSecRandomDefault,
        bytes.count,
        &bytes
    )
    guard status == errSecSuccess else {
        throw BrokerFailure.security(
            "generate native bootstrap session nonce",
            status
        )
    }
    return Data(bytes).map {
        String(format: "%02x", $0)
    }.joined()
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

func configureSessionTimeout(
    _ descriptor: Int32,
    milliseconds: Int = 5_000
) throws {
    var timeout = timeval(
        tv_sec: milliseconds / 1_000,
        tv_usec: Int32((milliseconds % 1_000) * 1_000)
    )
    for option in [SO_RCVTIMEO, SO_SNDTIMEO] {
        guard setsockopt(
            descriptor,
            SOL_SOCKET,
            option,
            &timeout,
            socklen_t(MemoryLayout<timeval>.size)
        ) == 0 else {
            throw BrokerFailure.capability(
                "configure authority session timeout: errno \(errno)"
            )
        }
    }
}

func writeSessionBytes(_ data: Data, to descriptor: Int32) throws {
    try data.withUnsafeBytes { buffer in
        guard let base = buffer.baseAddress else { return }
        var offset = 0
        while offset < data.count {
            let written = Darwin.write(
                descriptor,
                base.advanced(by: offset),
                data.count - offset
            )
            if written < 0 && errno == EINTR { continue }
            guard written > 0 else {
                throw BrokerFailure.capability(
                    "write authority session: errno \(errno)"
                )
            }
            offset += written
        }
    }
}

func readSessionBytes(
    count: Int,
    from descriptor: Int32
) throws -> Data {
    var result = Data(count: count)
    var offset = 0
    try result.withUnsafeMutableBytes { buffer in
        guard let base = buffer.baseAddress else { return }
        while offset < count {
            let received = Darwin.read(
                descriptor,
                base.advanced(by: offset),
                count - offset
            )
            if received < 0 && errno == EINTR { continue }
            guard received > 0 else {
                throw BrokerFailure.capability(
                    received == 0
                        ? "authority session closed"
                        : "read authority session: errno \(errno)"
                )
            }
            offset += received
        }
    }
    return result
}

func writeSessionFrame(_ data: Data, to descriptor: Int32) throws {
    guard !data.isEmpty, data.count <= maximumRequestBytes else {
        throw BrokerFailure.invalidRequest(
            "authority session frame exceeds size limit"
        )
    }
    var length = UInt32(data.count).bigEndian
    try withUnsafeBytes(of: &length) {
        try writeSessionBytes(Data($0), to: descriptor)
    }
    try writeSessionBytes(data, to: descriptor)
}

func readSessionFrame(from descriptor: Int32) throws -> Data {
    let prefix = try readSessionBytes(count: 4, from: descriptor)
    let length = prefix.withUnsafeBytes {
        $0.load(as: UInt32.self).bigEndian
    }
    guard length > 0, length <= maximumRequestBytes else {
        throw BrokerFailure.invalidRequest(
            "authority session frame exceeds size limit"
        )
    }
    return try readSessionBytes(
        count: Int(length),
        from: descriptor
    )
}

func brokerURL() throws -> URL {
    try currentExecutableURL()
        .deletingLastPathComponent()
        .appendingPathComponent("macos-broker-internal")
}

func pinnedBrokerIdentity(
    from request: BootstrapRequest
) throws -> (requirement: String, codeHash: String, digest: String) {
    let data = try canonicalJSON(request.finalPlan)
    guard
        let plan = try JSONSerialization.jsonObject(with: data)
            as? [String: Any],
        let descriptor = plan["authority_bootstrap"]
            as? [String: Any],
        let identity = descriptor["native_broker_code_identity"]
            as? String,
        identity.hasPrefix("designated:"),
        let codeHash = descriptor[
            "native_broker_code_directory_hash"
        ] as? String,
        let digest = descriptor["native_broker_content_digest"]
            as? String
    else {
        throw BrokerFailure.capability(
            "verified plan broker pins are unavailable"
        )
    }
    return (
        String(identity.dropFirst("designated:".count)),
        codeHash,
        digest
    )
}

func sessionSignaturePayload(
    protocolVersion: Int,
    operation: String,
    recovery: Bool,
    verifierNonce: String,
    brokerNonce: String,
    requestDigest: String,
    finalPlanDigest: String,
    manifest: BootstrapManifest?
) throws -> Data {
    var object: [String: Any] = [
        "protocol_version": protocolVersion,
        "operation": operation,
        "recovery": recovery,
        "verifier_nonce": verifierNonce,
        "broker_nonce": brokerNonce,
        "request_digest": requestDigest,
        "final_plan_digest": finalPlanDigest,
    ]
    if let manifest {
        object["manifest"] = try JSONSerialization.jsonObject(
            with: canonicalJSON(manifest)
        )
    } else {
        object["manifest"] = NSNull()
    }
    return try canonicalJSONObject(object)
}

func sessionSignature(
    protocolVersion: Int,
    operation: String,
    recovery: Bool,
    verifierNonce: String,
    brokerNonce: String,
    requestDigest: String,
    finalPlanDigest: String,
    manifest: BootstrapManifest?
) throws -> String {
    sha256(
        Data("agent-harness/bootstrap-session-response/v1\0".utf8)
            + (try sessionSignaturePayload(
                protocolVersion: protocolVersion,
                operation: operation,
                recovery: recovery,
                verifierNonce: verifierNonce,
                brokerNonce: brokerNonce,
                requestDigest: requestDigest,
                finalPlanDigest: finalPlanDigest,
                manifest: manifest
            ))
    )
}

func terminateAndWait(_ process: Process) {
    if process.isRunning {
        _ = kill(process.processIdentifier, SIGKILL)
    }
    process.waitUntilExit()
}

func signedMemoryVerifierTestControl(_ name: String) throws -> String? {
    #if AGENT_HARNESS_VERIFIER_ROLE && AGENT_HARNESS_SIGNED_MEMORY_PROVIDER
    guard try authorityProvider() == "signed-memory",
          try verifierMode() == "test" else {
        return nil
    }
    let url = URL(fileURLWithPath: try signedMemoryStatePath())
        .deletingLastPathComponent()
        .appendingPathComponent(name)
    guard FileManager.default.fileExists(atPath: url.path) else {
        return nil
    }
    let data = try Data(contentsOf: url)
    guard data.count <= 4_096,
          let value = String(data: data, encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines),
          !value.isEmpty else {
        throw BrokerFailure.capability(
            "signed-memory verifier test control is malformed"
        )
    }
    return value
    #else
    _ = name
    return nil
    #endif
}

func verifierBootstrapBrokerURL() throws -> URL {
    guard let alternate = try signedMemoryVerifierTestControl(
        "alternate-broker-path"
    ) else {
        return try brokerURL()
    }
    guard alternate.hasPrefix("/") else {
        throw BrokerFailure.capability(
            "alternate signed-memory broker path must be absolute"
        )
    }
    let url = URL(fileURLWithPath: alternate)
        .resolvingSymlinksInPath()
        .standardizedFileURL
    return url
}

func verifierBootstrapResponseMutation() throws -> String? {
    guard let mutation = try signedMemoryVerifierTestControl(
        "response-mutation"
    ) else {
        return nil
    }
    guard [
        "response-operation",
        "response-recovery",
        "response-nonce",
        "response-request-digest",
        "response-plan-digest",
    ].contains(mutation) else {
        throw BrokerFailure.capability(
            "signed-memory response mutation is invalid"
        )
    }
    return mutation
}

func runVerifierBootstrapCommand(
    _ command: String,
    arguments: [String]
) throws {
    guard arguments.count == 1 else {
        throw BrokerFailure.invalidRequest(
            "bootstrap arguments are invalid"
        )
    }
    let requestData = try readBootstrapVerifierRequest()
    let request = try decodeRequest(
        BootstrapRequest.self,
        from: requestData
    )
    guard try canonicalJSON(request) == requestData else {
        throw BrokerFailure.invalidRequest(
            "bootstrap request must be canonical JSON"
        )
    }
    let attestation = try verifyBootstrapForMutation(request)
    let controller = try readControllerRelease()
    defer { close(controller.descriptor) }
    let authorization: ControllerAuthorization?
    if command == "bootstrap" {
        let decoded = try decodeRequest(
            ControllerAuthorization.self,
            from: controller.data
        )
        guard try canonicalJSON(decoded) == controller.data else {
            throw BrokerFailure.invalidRequest(
                "controller authorization must be canonical JSON"
            )
        }
        try verifyControllerAuthorization(
            decoded,
            request: request,
            operation: command,
            attestation: attestation
        )
        authorization = decoded
    } else {
        let release = try decodeRequest(
            ControllerRecoveryRelease.self,
            from: controller.data
        )
        guard try canonicalJSON(release) == controller.data,
              release == (try expectedControllerRecoveryRelease(
                request: request,
                attestation: attestation
              )) else {
            throw BrokerFailure.capability(
                "controller recovery release binding mismatch"
            )
        }
        authorization = nil
    }
    let manifest = try runVerifierBrokerSession(
        request: request,
        operation: command,
        recovery: command == "bootstrap-recover",
        broker: try verifierBootstrapBrokerURL(),
        testResponseMutation: try verifierBootstrapResponseMutation(),
        controllerAuthorization: authorization,
        controllerDescriptor: controller.descriptor
    )
    FileHandle.standardOutput.write(try canonicalJSON(manifest))
    FileHandle.standardOutput.write(Data([0x0a]))
}

func runVerifierBrokerSession(
    request: BootstrapRequest,
    operation: String,
    recovery: Bool,
    broker executable: URL,
    testResponseMutation: String? = nil,
    controllerAuthorization: ControllerAuthorization? = nil,
    controllerDescriptor: Int32? = nil
) throws -> BootstrapManifest {
    let requestDigest = sha256(try canonicalJSON(request))
    let verifierNonce = try controllerAuthorization?.controllerNonce
        ?? randomSessionNonce()
    let sessionRequest = BrokerSessionRequest(
        protocolVersion: 1,
        operation: operation,
        recovery: recovery,
        verifierNonce: verifierNonce,
        requestDigest: requestDigest,
        finalPlanDigest: request.finalPlanDigest,
        request: request,
        controllerAuthorization: controllerAuthorization,
        testResponseMutation: testResponseMutation
    )
    var sockets: [Int32] = [0, 0]
    guard socketpair(AF_UNIX, SOCK_STREAM, 0, &sockets) == 0 else {
        throw BrokerFailure.capability(
            "create authority broker session: errno \(errno)"
        )
    }
    let process = Process()
    process.executableURL = executable
    process.arguments = ["--broker-session"]
    process.environment = ["PATH": "/usr/bin:/bin:/usr/sbin:/sbin"]
    let brokerHandle = FileHandle(
        fileDescriptor: sockets[1],
        closeOnDealloc: false
    )
    process.standardInput = brokerHandle
    process.standardOutput = brokerHandle
    let errorPipe = Pipe()
    process.standardError = errorPipe
    do {
        try process.run()
    } catch {
        close(sockets[0])
        close(sockets[1])
        throw error
    }
    close(sockets[1])
    defer { close(sockets[0]) }
    do {
        if let controllerDescriptor {
            try requireControllerSessionAlive(controllerDescriptor)
        }
        try configureSessionTimeout(sockets[0])
        let expected = try pinnedBrokerIdentity(from: request)
        try authenticateLiveProcess(
            process.processIdentifier,
            expectedRequirement: expected.requirement,
            expectedCodeDirectoryHash: expected.codeHash
        )
        if let controllerDescriptor {
            try requireControllerSessionAlive(controllerDescriptor)
        }
        try writeSessionFrame(
            try canonicalJSON(sessionRequest),
            to: sockets[0]
        )
        let commitData = try readSessionFrame(from: sockets[0])
        let commit = try decodeRequest(
            BrokerSessionCommit.self,
            from: commitData
        )
        guard try canonicalJSON(commit) == commitData,
              commit.protocolVersion == 1,
              commit.operation == operation,
              commit.recovery == recovery,
              commit.verifierNonce == verifierNonce,
              hexadecimalData(commit.brokerNonce)?.count == 32,
              commit.requestDigest == requestDigest,
              commit.finalPlanDigest == request.finalPlanDigest else {
            throw BrokerFailure.capability(
                "authority broker commit binding mismatch"
            )
        }
        try writeSessionFrame(commitData, to: sockets[0])
        let responseData = try readSessionFrame(from: sockets[0])
        let response = try decodeRequest(
            BrokerSessionResponse.self,
            from: responseData
        )
        guard try canonicalJSON(response) == responseData,
              response.protocolVersion == 1,
              response.operation == operation,
              response.recovery == recovery,
              response.verifierNonce == verifierNonce,
              response.brokerNonce == commit.brokerNonce,
              response.requestDigest == requestDigest,
              response.finalPlanDigest == request.finalPlanDigest,
              let manifest = response.manifest,
              manifest.pendingPlanCommitment
                == request.finalPlanDigest,
              response.signature == (try sessionSignature(
                protocolVersion: response.protocolVersion,
                operation: response.operation,
                recovery: response.recovery,
                verifierNonce: response.verifierNonce,
                brokerNonce: response.brokerNonce,
                requestDigest: response.requestDigest,
                finalPlanDigest: response.finalPlanDigest,
                manifest: manifest
              )) else {
            throw BrokerFailure.capability(
                "authority broker response binding mismatch"
            )
        }
        if try authorityProvider() == "signed-memory" {
            try incrementSignedMemoryState("accepted_response_count")
        }
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            throw BrokerFailure.capability(
                "authority broker exited unsuccessfully"
            )
        }
        return manifest
    } catch {
        terminateAndWait(process)
        let brokerError =
            errorPipe.fileHandleForReading.readDataToEndOfFile()
        if let detail = String(data: brokerError, encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines),
           !detail.isEmpty {
            throw BrokerFailure.capability(detail)
        }
        throw error
    }
}

func runBrokerSession() throws {
    try configureSessionTimeout(STDIN_FILENO)
    let parentPID = try authenticateLivePeer(
        socket: STDIN_FILENO,
        expectedRequirement: try signedMetadataString(
            "AgentHarnessTrustedVerifierRequirement"
        ),
        expectedCodeDirectoryHash: try signedMetadataString(
            "AgentHarnessTrustedVerifierCodeHash"
        ),
        requireParent: true
    )
    if try authorityProvider() == "signed-memory" {
        try withSignedMemoryState { state in
            state["broker_pid"] = Int(getpid())
            state["broker_started"] = true
        }
    }
    let requestData = try readSessionFrame(from: STDIN_FILENO)
    let session = try decodeRequest(
        BrokerSessionRequest.self,
        from: requestData
    )
    guard try canonicalJSON(session) == requestData,
          session.protocolVersion == 1,
          ["bootstrap", "bootstrap-recover"]
            .contains(session.operation),
          session.recovery
            == (session.operation == "bootstrap-recover"),
          hexadecimalData(session.verifierNonce)?.count == 32,
          session.requestDigest
            == sha256(try canonicalJSON(session.request)),
          session.finalPlanDigest
            == session.request.finalPlanDigest else {
        throw BrokerFailure.capability(
            "authority broker request binding mismatch"
        )
    }
    let attestation = try brokerAttestation()
    let acceptedAuthorization: ControllerAuthorization?
    _ = try validateBootstrapPlan(
        session.request,
        attestation: attestation
    )
    if session.recovery {
        guard session.controllerAuthorization == nil else {
            throw BrokerFailure.capability(
                "recovery cannot replace controller authorization"
            )
        }
        let reserved = try reservedControllerAuthorization(
            request: session.request
        )
        try verifyControllerAuthorization(
            reserved,
            request: session.request,
            operation: "bootstrap",
            attestation: attestation
        )
        acceptedAuthorization = reserved
    } else {
        guard
            let controllerAuthorization =
                session.controllerAuthorization,
            controllerAuthorization.controllerNonce
                == session.verifierNonce
        else {
            throw BrokerFailure.capability(
                "controller authorization is required"
            )
        }
        try verifyControllerAuthorization(
            controllerAuthorization,
            request: session.request,
            operation: session.operation,
            attestation: attestation
        )
        acceptedAuthorization = controllerAuthorization
    }
    let brokerNonce = try randomSessionNonce()
    let commit = BrokerSessionCommit(
        protocolVersion: 1,
        operation: session.operation,
        recovery: session.recovery,
        verifierNonce: session.verifierNonce,
        brokerNonce: brokerNonce,
        requestDigest: session.requestDigest,
        finalPlanDigest: session.finalPlanDigest
    )
    let commitData = try canonicalJSON(commit)
    try writeSessionFrame(commitData, to: STDOUT_FILENO)
    let echoedCommit = try readSessionFrame(from: STDIN_FILENO)
    guard echoedCommit == commitData else {
        throw BrokerFailure.capability(
            "authority broker commit was not authorized"
        )
    }
    try requireAuthenticatedParentAlive(
        parentPID,
        socket: STDIN_FILENO
    )
    guard let controllerAuthorization = acceptedAuthorization else {
        throw BrokerFailure.capability(
            "controller authorization is required"
        )
    }
    if !session.recovery,
       try authorityProvider() == "signed-memory" {
        try reserveSignedMemoryDispatch(
            session,
            brokerNonce: brokerNonce
        )
    }
    let manifest = try mutateBootstrapForProvider(
        session.request,
        allowExisting: session.recovery,
        attestation: attestation,
        authorization: controllerAuthorization,
        parentPID: parentPID,
        socket: STDIN_FILENO
    )
    var responseOperation = session.operation
    var responseRecovery = session.recovery
    var responseVerifierNonce = session.verifierNonce
    var responseRequestDigest = session.requestDigest
    var responsePlanDigest = session.finalPlanDigest
    switch session.testResponseMutation {
    case "response-operation":
        responseOperation = "tampered-operation"
    case "response-recovery":
        responseRecovery.toggle()
    case "response-nonce":
        responseVerifierNonce = String(repeating: "0", count: 64)
    case "response-request-digest":
        responseRequestDigest = String(repeating: "0", count: 64)
    case "response-plan-digest":
        responsePlanDigest = String(repeating: "0", count: 64)
    case nil:
        break
    default:
        throw BrokerFailure.invalidRequest(
            "unknown protocol response mutation"
        )
    }
    let signature = try sessionSignature(
        protocolVersion: 1,
        operation: responseOperation,
        recovery: responseRecovery,
        verifierNonce: responseVerifierNonce,
        brokerNonce: brokerNonce,
        requestDigest: responseRequestDigest,
        finalPlanDigest: responsePlanDigest,
        manifest: manifest
    )
    let response = BrokerSessionResponse(
        protocolVersion: 1,
        operation: responseOperation,
        recovery: responseRecovery,
        verifierNonce: responseVerifierNonce,
        brokerNonce: brokerNonce,
        requestDigest: responseRequestDigest,
        finalPlanDigest: responsePlanDigest,
        manifest: manifest,
        signature: signature
    )
    try writeSessionFrame(
        try canonicalJSON(response),
        to: STDOUT_FILENO
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
    let selfTestLauncherDigest = String(repeating: "a", count: 64)
    let selfTestNativeDigest = String(repeating: "0", count: 64)
    let manifest = BootstrapManifest(
        schema: "agent-harness/authority-manifest",
        schemaVersion: 1,
        createdAt: "2000-01-01T00:00:00Z",
        installationId: "00000000-0000-4000-8000-000000000000",
        launcherCodeIdentity: "sha256:\(selfTestLauncherDigest)",
        launcherContentDigest: selfTestLauncherDigest,
        nativeBrokerCodeIdentity: "self-test-native",
        nativeBrokerContentDigest: selfTestNativeDigest,
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
          manifestObject["launcher_content_digest"] as? String
              == selfTestLauncherDigest,
          manifestObject["native_broker_content_digest"] as? String
              == selfTestNativeDigest,
          selfTestLauncherDigest != selfTestNativeDigest,
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
        _ = try readBootstrapVerifierRequest()
        rawBootstrapRejected = false
    } catch {
        rawBootstrapRejected = true
    }
    let liveAttestation = try brokerAttestation()
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
        "launcher_native_binding_valid":
            liveAttestation.launcherContentDigest
                != liveAttestation.nativeBrokerContentDigest,
        "manifest_contract_valid": true,
        "keychain_mutated": false,
        "user_presence_requested": false,
    ]
    FileHandle.standardOutput.write(try canonicalJSONObject(evidence))
    FileHandle.standardOutput.write(Data([0x0a]))
}
