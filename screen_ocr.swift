import Foundation
import Vision
import AppKit

// Normalized top-left coordinates match mac_gesture.click_ratio.
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["ko-KR", "en-US"]
try VNImageRequestHandler(url: url).perform([request])
let rows: [[String: Any]] = (request.results ?? []).compactMap { observation in
    guard let text = observation.topCandidates(1).first?.string else { return nil }
    let box = observation.boundingBox
    return ["text": text, "x": box.midX, "y": 1 - box.midY,
            "width": box.width, "height": box.height]
}
// Sample the colored button background, independently of its OCR label.
let bitmap = NSBitmapImageRep(data: try Data(contentsOf: url))!
func activeFraction(_ rect: [Double]) -> Double {
    var active = 0
    for y in 0..<12 {
        for x in 0..<24 {
            let px = Int((rect[0] + rect[2] * (Double(x) + 0.5) / 24) * Double(bitmap.pixelsWide))
            let py = Int((rect[1] + rect[3] * (Double(y) + 0.5) / 12) * Double(bitmap.pixelsHigh))
            if let color = bitmap.colorAt(x: px, y: py)?.usingColorSpace(.deviceRGB) {
                let r = color.redComponent, g = color.greenComponent, b = color.blueComponent
                if g > 0.48 && max(r, g, b) - min(r, g, b) > 0.30 { active += 1 }
            }
        }
    }
    return Double(active) / 288
}
let result: [String: Any] = ["rows": rows, "active": [
    "friend_bulk": activeFraction([0.690, 0.854, 0.140, 0.040]),
    "journey_accelerate": activeFraction([0.712, 0.511, 0.095, 0.035])
]]
FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: result))
