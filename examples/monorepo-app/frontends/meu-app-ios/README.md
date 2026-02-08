# Meu App iOS

Placeholder para aplicação iOS nativa ou React Native/Flutter.

## Estrutura Sugerida

```
meu-app-ios/
├── MeuApp.xcodeproj/  # Projeto Xcode
├── MeuApp/            # Código fonte Swift
├── MeuAppTests/       # Testes unitários
├── MeuAppUITests/     # Testes de UI
└── Podfile            # CocoaPods (se usado)
```

## Stack Recomendada

- **SwiftUI** (iOS nativo) ou
- **React Native** (compartilhar código com Android) ou
- **Flutter** (compartilhar código com Android)

## Integração com API

```swift
// Exemplo: URLSession com o backend Go
struct ApiClient {
    static let baseURL = URL(string: "https://api.meuapp.com")!
    
    static func login(email: String, password: String) async throws -> AuthResponse {
        var request = URLRequest(url: baseURL.appendingPathComponent("/api/v1/auth/login"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(LoginRequest(email: email, password: password))
        
        let (data, _) = try await URLSession.shared.data(for: request)
        return try JSONDecoder().decode(AuthResponse.self, from: data)
    }
}
```

## Build

```bash
# Simulador
xcodebuild -scheme MeuApp -destination 'platform=iOS Simulator,name=iPhone 16'

# Archive para App Store
xcodebuild -scheme MeuApp -archivePath build/MeuApp.xcarchive archive
```

## CI/CD

O pipeline de iOS está configurado em `.github/workflows/ci-mobile.yml`.
Requer macOS runner com Xcode instalado.
