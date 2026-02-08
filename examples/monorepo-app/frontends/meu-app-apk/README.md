# Meu App APK (Android)

Placeholder para aplicação Android nativa ou React Native/Flutter.

## Estrutura Sugerida

```
meu-app-apk/
├── android/           # Projeto Android nativo
├── src/               # Código compartilhado (React Native/Flutter)
├── build.gradle       # Config Gradle
└── Makefile           # Atalhos de build
```

## Stack Recomendada

- **React Native** (compartilhar código com iOS) ou
- **Flutter** (compartilhar código com iOS) ou
- **Kotlin + Jetpack Compose** (Android nativo)

## Integração com API

```kotlin
// Exemplo: Retrofit com o backend Go
val api = Retrofit.Builder()
    .baseUrl("https://api.meuapp.com")
    .addConverterFactory(GsonConverterFactory.create())
    .build()
    .create(ApiService::class.java)
```

## Build

```bash
# Debug APK
./gradlew assembleDebug

# Release APK (assinado)
./gradlew assembleRelease
```

## CI/CD

O pipeline de Android está configurado em `.github/workflows/ci-mobile.yml`.
O APK é gerado automaticamente em cada push na branch `develop`.
