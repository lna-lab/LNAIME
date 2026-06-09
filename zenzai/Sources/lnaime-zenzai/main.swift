// =============================================================================
// LNAIME Tier-2 faithful kana→kanji wrapper around AzooKey Zenzai.
//
// FAITHFULNESS GUARANTEE: the classical dictionary lattice proposes candidates
// and zenz only re-ranks them; we keep only candidates whose concatenated ruby
// (katakana) == the input katakana. That equality filter guarantees output
// reading == input kana.
//
// L0 dict injection: importDynamicUserDictionary — reading MUST be katakana,
// cid=固有名詞(1288), mid=一般, value=-10 (bias).
//
// GPU: ZenzaiMode.on(..., deviceConfig: createDeviceConfig(deviceName:"CUDA0",
// gpuLayers:99)). DeviceConfig() default gpuLayers=0 (=CPU) — always route via
// createDeviceConfig (default 99).
//
// Wire: JSON-Lines over stdio. One request per line in, one response per line out.
// =============================================================================
import Foundation
#if canImport(Glibc)
import Glibc
#endif
import KanaKanjiConverterModuleWithDefaultDictionary
import KanaKanjiConverterModule
import SwiftUtils

struct UserDictItem: Codable { var word: String; var reading: String; var hint: String? }
struct ConvRequest: Codable {
    var reading: String
    var n: Int?
    var userdict: [UserDictItem]?
    var left: String?
    var profile: String?
}
struct OutCand: Codable { var text: String; var value: Double }
struct ConvResponse: Codable {
    var ok: Bool
    var reading: String
    var candidates: [OutCand]
    var best: String?
    var faithful: Bool?
    var error: String?
}

final class FaithfulConverter {
    let converter: KanaKanjiConverter
    let gguf: URL
    let device: String
    let dictValue: Double
    let inferenceLimit: Int

    init(gguf: URL, device: String, dictValue: Double, inferenceLimit: Int) {
        self.converter = KanaKanjiConverter.withDefaultDictionary()
        self.gguf = gguf
        self.device = device
        self.dictValue = dictValue
        self.inferenceLimit = inferenceLimit
    }

    func loadUserDict(_ items: [UserDictItem]) {
        let dic: [DicdataElement] = items.map {
            DicdataElement(
                word: $0.word,
                ruby: $0.reading.toKatakana(),
                cid: CIDData.固有名詞.cid,
                mid: MIDData.一般.mid,
                value: PValue(dictValue)
            )
        }
        converter.importDynamicUserDictionary(dic)
    }

    func options(n: Int, left: String?, profile: String?) -> ConvertRequestOptions {
        ConvertRequestOptions(
            N_best: n,
            needTypoCorrection: false,
            requireJapanesePrediction: .disabled,
            requireEnglishPrediction: .disabled,
            keyboardLanguage: .ja_JP,
            englishCandidateInRoman2KanaInput: false,
            fullWidthRomanCandidate: false,
            halfWidthKanaCandidate: false,
            learningType: .nothing,
            maxMemoryCount: 0,
            shouldResetMemory: false,
            memoryDirectoryURL: URL(fileURLWithPath: NSTemporaryDirectory()),
            sharedContainerURL: URL(fileURLWithPath: NSTemporaryDirectory()),
            textReplacer: .empty,
            specialCandidateProviders: [],
            zenzaiMode: .on(
                weight: gguf,
                inferenceLimit: inferenceLimit,
                requestRichCandidates: false,
                personalizationMode: nil,
                versionDependentMode: .v3(.init(
                    profile: profile,
                    topic: nil, style: nil, preference: nil,
                    leftSideContext: left
                )),
                deviceConfig: createDeviceConfig(deviceName: device, gpuLayers: 99)
            ),
            preloadDictionary: false,
            metadata: .init(versionString: "LNAIME-Zenzai 0.1")
        )
    }

    func convert(_ req: ConvRequest) -> ConvResponse {
        let target = req.reading.toKatakana()
        let n = req.n ?? 8
        if let ud = req.userdict, !ud.isEmpty { loadUserDict(ud) }

        var c = ComposingText()
        c.insertAtCursorPosition(req.reading, inputStyle: .direct)

        let result = converter.requestCandidates(
            c.prefixToCursorPosition(),
            options: options(n: n, left: req.left, profile: req.profile)
        )

        let faithfulCands = result.mainResults.filter { cand in
            cand.data.reduce(into: "") { $0 += $1.ruby } == target
        }
        let isFaithful = !faithfulCands.isEmpty
        let chosen = isFaithful ? faithfulCands : result.mainResults
        let out = chosen.map { OutCand(text: $0.text, value: Double($0.value)) }

        converter.stopComposition()
        return ConvResponse(ok: true, reading: target, candidates: out,
                            best: out.first?.text, faithful: isFaithful, error: nil)
    }
}

let env = ProcessInfo.processInfo.environment
let gguf = URL(fileURLWithPath: env["ZENZ_WEIGHT"] ?? "/models/zenz.gguf")
let device = env["ZENZ_DEVICE"] ?? "CUDA0"

loadGGMLBackends(from: env["GGML_BACKEND_DIR"])
for d in enumerateGGMLBackendDevices() {
    FileHandle.standardError.write("device: \(d.name)\n".data(using: .utf8)!)
}

let dictValue = Double(env["LNAIME_DICT_VALUE"] ?? "") ?? -10
let inferenceLimit = Int(env["LNAIME_INFERENCE_LIMIT"] ?? "") ?? 1
let engine = FaithfulConverter(gguf: gguf, device: device,
                               dictValue: dictValue, inferenceLimit: inferenceLimit)
let encoder = JSONEncoder()
let decoder = JSONDecoder()

@MainActor func responseData(forLine line: String) -> Data {
    let resp: ConvResponse
    if let data = line.data(using: .utf8),
       let req = try? decoder.decode(ConvRequest.self, from: data) {
        resp = engine.convert(req)
    } else {
        resp = ConvResponse(ok: false, reading: "", candidates: [], best: nil,
                            faithful: nil, error: "bad JSON request")
    }
    return (try? encoder.encode(resp)) ?? Data("{\"ok\":false}".utf8)
}

// JSON-Lines over TCP (resident, single connection at a time — fine for an IME).
@MainActor func serveTCP(port: UInt16) {
    let listenFD = socket(AF_INET, Int32(SOCK_STREAM.rawValue), 0)
    precondition(listenFD >= 0, "socket() failed")
    var yes: Int32 = 1
    setsockopt(listenFD, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))
    var addr = sockaddr_in()
    addr.sin_family = sa_family_t(AF_INET)
    addr.sin_port = port.bigEndian
    addr.sin_addr.s_addr = in_addr_t(0)   // INADDR_ANY
    let bound = withUnsafePointer(to: &addr) {
        $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            bind(listenFD, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
        }
    }
    precondition(bound == 0, "bind() failed")
    precondition(listen(listenFD, 16) == 0, "listen() failed")
    FileHandle.standardError.write("LNAIME-Zenzai TCP listening on :\(port)\n".data(using: .utf8)!)
    while true {
        let clientFD = accept(listenFD, nil, nil)
        if clientFD < 0 { continue }
        var buffer = [UInt8]()
        var tmp = [UInt8](repeating: 0, count: 8192)
        readLoop: while true {
            while let nl = buffer.firstIndex(of: 0x0A) {
                let lineBytes = Array(buffer[0..<nl])
                buffer.removeSubrange(0...nl)
                guard let line = String(bytes: lineBytes, encoding: .utf8), !line.isEmpty else { continue }
                var out = responseData(forLine: line)
                out.append(0x0A)
                out.withUnsafeBytes { ptr in _ = write(clientFD, ptr.baseAddress, ptr.count) }
            }
            let n = read(clientFD, &tmp, tmp.count)
            if n <= 0 { break readLoop }
            buffer.append(contentsOf: tmp[0..<n])
        }
        close(clientFD)
    }
}

FileHandle.standardError.write("LNAIME-Zenzai ready (device=\(device), weight=\(gguf.path))\n".data(using: .utf8)!)
if let portStr = env["LNAIME_TCP_PORT"], let port = UInt16(portStr) {
    serveTCP(port: port)
} else {
    while let line = readLine(strippingNewline: true) {
        if line.isEmpty { continue }
        FileHandle.standardOutput.write(responseData(forLine: line))
        FileHandle.standardOutput.write("\n".data(using: .utf8)!)
    }
}
