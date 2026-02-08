FROM mcr.microsoft.com/dotnet/sdk:9.0 AS builder
WORKDIR /app
COPY *.csproj ./
RUN dotnet restore
COPY . .
RUN dotnet publish -c Release -o /out --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:9.0
RUN groupadd -g 1000 app && useradd -u 1000 -g app -s /bin/bash app
WORKDIR /app
COPY --from=builder /out .
RUN chown -R app:app /app
USER app
EXPOSE 8082
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8082/health || exit 1
ENTRYPOINT ["dotnet", "ApiDotnet.dll"]
