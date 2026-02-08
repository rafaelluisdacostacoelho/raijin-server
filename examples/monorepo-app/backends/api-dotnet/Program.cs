using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using System;

var builder = WebApplication.CreateBuilder(args);

var corsOrigins = Environment.GetEnvironmentVariable("CORS_ORIGINS") ?? "http://localhost:5173";

builder.Services.AddCors(options =>
{
    options.AddPolicy("AllowFrontend", policy =>
    {
        policy.WithOrigins(corsOrigins.Split(","))
              .AllowAnyMethod()
              .AllowAnyHeader()
              .AllowCredentials();
    });
});

var app = builder.Build();

app.UseCors("AllowFrontend");

app.MapGet("/health", () => Results.Ok(new
{
    status = "healthy",
    service = "api-dotnet",
    version = "1.0.0",
    timestamp = DateTime.UtcNow.ToString("o")
}));

app.MapGet("/ready", () => Results.Ok(new { status = "ready" }));

app.MapGet("/api/v1/messages", () => Results.Ok(new
{
    messages = new[]
    {
        new { id = 1, text = "Hello from C# API!", created_at = DateTime.UtcNow.ToString("o") },
        new { id = 2, text = "This is a .NET 9 Minimal API", created_at = DateTime.UtcNow.ToString("o") }
    }
}));

app.MapPost("/api/v1/messages", (MessageRequest req) =>
{
    return Results.Created($"/api/v1/messages/1", new
    {
        id = new Random().Next(1, 10000),
        text = req.Text,
        created_at = DateTime.UtcNow.ToString("o")
    });
});

app.Run($"http://0.0.0.0:{Environment.GetEnvironmentVariable("SERVER_PORT") ?? "8082"}");

record MessageRequest(string Text);
