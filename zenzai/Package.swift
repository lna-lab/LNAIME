// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "lnaime-zenzai",
    platforms: [.macOS(.v13)],
    traits: [
        "Zenzai"
    ],
    dependencies: [
        // Path dependency to the cloned fork (/src/converter @ 8b4befc).
        // Forward OUR "Zenzai" trait to the converter so it links llama.cpp + GPU path.
        .package(
            path: "/src/converter",
            traits: [.trait(name: "Zenzai", condition: .when(traits: ["Zenzai"]))]
        ),
        // Pin to hazkey's known-good version. 1.6.0 (latest) breaks the converter's
        // transitive `import Collections` re-export under MemberImportVisibility.
        .package(url: "https://github.com/apple/swift-collections", exact: "1.2.1"),
    ],
    targets: [
        .executableTarget(
            name: "lnaime-zenzai",
            dependencies: [
                .product(name: "KanaKanjiConverterModuleWithDefaultDictionary",
                         package: "converter"),
                .product(name: "KanaKanjiConverterModule",
                         package: "converter"),
                .product(name: "SwiftUtils", package: "converter"),
            ],
            swiftSettings: [
                .interoperabilityMode(.Cxx)
            ],
            linkerSettings: [
                .unsafeFlags(["-Xlinker", "-rpath", "-Xlinker", "$ORIGIN/libllama"])
            ]
        )
    ]
)
