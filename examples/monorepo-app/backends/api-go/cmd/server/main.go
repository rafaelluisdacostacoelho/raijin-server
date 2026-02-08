package main

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"golang.org/x/crypto/bcrypt"
)

// ===========================================================================
// Build info
// ===========================================================================

var (
	Version   = "dev"
	BuildTime = "unknown"
	startTime = time.Now()
)

// ===========================================================================
// Configuration
// ===========================================================================

type Config struct {
	Port           string
	Environment    string
	AllowedOrigins []string
	JWTSecret      string
}

func LoadConfig() *Config {
	origins := getEnv("CORS_ORIGINS", "http://localhost:5173")
	port := getEnv("SERVER_PORT", "8080")
	env := getEnv("SERVER_ENVIRONMENT", "development")
	jwtSecret := getEnv("JWT_SECRET", "dev-jwt-secret-CHANGE-IN-PRODUCTION")

	return &Config{
		Port:           port,
		Environment:    env,
		AllowedOrigins: strings.Split(origins, ","),
		JWTSecret:      jwtSecret,
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// ===========================================================================
// Models
// ===========================================================================

type User struct {
	ID        string    `json:"id"`
	Email     string    `json:"email"`
	Name      string    `json:"name"`
	Role      string    `json:"role"`
	Password  string    `json:"-"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type LoginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type RegisterRequest struct {
	Email    string `json:"email"`
	Name     string `json:"name"`
	Password string `json:"password"`
}

type AuthResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	User         User   `json:"user"`
	CSRFToken    string `json:"csrf_token"`
}

type APIError struct {
	Error   string `json:"error"`
	Message string `json:"message"`
	Code    int    `json:"code"`
}

type HealthResponse struct {
	Status    string `json:"status"`
	Version   string `json:"version"`
	Timestamp string `json:"timestamp"`
	Uptime    string `json:"uptime"`
}

// ===========================================================================
// In-Memory Store (swap for PostgreSQL/pgx in production)
// ===========================================================================

type Store struct {
	mu            sync.RWMutex
	users         map[string]*User
	emailIndex    map[string]string
	refreshTokens map[string]string
	csrfTokens    map[string]time.Time
}

func NewStore() *Store {
	s := &Store{
		users:         make(map[string]*User),
		emailIndex:    make(map[string]string),
		refreshTokens: make(map[string]string),
		csrfTokens:    make(map[string]time.Time),
	}

	hashedPw, _ := bcrypt.GenerateFromPassword([]byte("admin123"), bcrypt.DefaultCost)
	adminID := generateID()
	now := time.Now()
	s.users[adminID] = &User{
		ID: adminID, Email: "admin@example.com", Name: "Admin",
		Role: "admin", Password: string(hashedPw),
		CreatedAt: now, UpdatedAt: now,
	}
	s.emailIndex["admin@example.com"] = adminID

	return s
}

func (s *Store) CreateUser(email, name, password, role string) (*User, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.emailIndex[email]; exists {
		return nil, fmt.Errorf("email already registered")
	}
	hashedPw, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return nil, err
	}
	id := generateID()
	now := time.Now()
	user := &User{
		ID: id, Email: email, Name: name, Role: role,
		Password: string(hashedPw), CreatedAt: now, UpdatedAt: now,
	}
	s.users[id] = user
	s.emailIndex[email] = id
	return user, nil
}

func (s *Store) GetUserByEmail(email string) (*User, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	id, ok := s.emailIndex[email]
	if !ok {
		return nil, fmt.Errorf("user not found")
	}
	return s.users[id], nil
}

func (s *Store) GetUserByID(id string) (*User, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	user, ok := s.users[id]
	if !ok {
		return nil, fmt.Errorf("user not found")
	}
	return user, nil
}

func (s *Store) ListUsers() []*User {
	s.mu.RLock()
	defer s.mu.RUnlock()
	users := make([]*User, 0, len(s.users))
	for _, u := range s.users {
		users = append(users, u)
	}
	return users
}

func (s *Store) StoreRefreshToken(token, userID string)       { s.mu.Lock(); s.refreshTokens[token] = userID; s.mu.Unlock() }
func (s *Store) ValidateRefreshToken(token string) (string, bool) { s.mu.RLock(); defer s.mu.RUnlock(); uid, ok := s.refreshTokens[token]; return uid, ok }
func (s *Store) RevokeRefreshToken(token string)              { s.mu.Lock(); delete(s.refreshTokens, token); s.mu.Unlock() }
func (s *Store) StoreCSRFToken(token string)                  { s.mu.Lock(); s.csrfTokens[token] = time.Now().Add(24 * time.Hour); s.mu.Unlock() }
func (s *Store) ValidateCSRFToken(token string) bool          { s.mu.RLock(); defer s.mu.RUnlock(); exp, ok := s.csrfTokens[token]; return ok && time.Now().Before(exp) }

// ===========================================================================
// JWT  (HS256 — stdlib only, zero deps)
// ===========================================================================

type JWTClaims struct {
	UserID string `json:"sub"`
	Email  string `json:"email"`
	Role   string `json:"role"`
	Exp    int64  `json:"exp"`
	Iat    int64  `json:"iat"`
}

func createJWT(secret string, claims JWTClaims) (string, error) {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"HS256","typ":"JWT"}`))
	claimsJSON, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}
	payload := base64.RawURLEncoding.EncodeToString(claimsJSON)
	signingInput := header + "." + payload
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(signingInput))
	signature := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
	return signingInput + "." + signature, nil
}

func verifyJWT(secret, tokenStr string) (*JWTClaims, error) {
	parts := strings.Split(tokenStr, ".")
	if len(parts) != 3 {
		return nil, fmt.Errorf("invalid token format")
	}
	signingInput := parts[0] + "." + parts[1]
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(signingInput))
	expectedSig := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
	if !hmac.Equal([]byte(parts[2]), []byte(expectedSig)) {
		return nil, fmt.Errorf("invalid signature")
	}
	claimsJSON, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return nil, fmt.Errorf("invalid payload")
	}
	var claims JWTClaims
	if err := json.Unmarshal(claimsJSON, &claims); err != nil {
		return nil, fmt.Errorf("invalid claims")
	}
	if time.Now().Unix() > claims.Exp {
		return nil, fmt.Errorf("token expired")
	}
	return &claims, nil
}

// ===========================================================================
// Utility
// ===========================================================================

func generateID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

func generateToken() string {
	b := make([]byte, 32)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

// ===========================================================================
// Middleware
// ===========================================================================

type contextKey string

const (
	ctxUserID contextKey = "user_id"
	ctxEmail  contextKey = "email"
	ctxRole   contextKey = "role"
)

type Middleware struct {
	cfg   *Config
	store *Store
}

func NewMiddleware(cfg *Config, store *Store) *Middleware {
	return &Middleware{cfg: cfg, store: store}
}

func (m *Middleware) SecurityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("X-Frame-Options", "DENY")
		w.Header().Set("X-XSS-Protection", "1; mode=block")
		w.Header().Set("Referrer-Policy", "strict-origin-when-cross-origin")
		w.Header().Set("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
		w.Header().Set("Content-Security-Policy",
			"default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "+
				"img-src 'self' data:; font-src 'self'; connect-src 'self'; "+
				"base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
		if m.cfg.Environment == "production" {
			w.Header().Set("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
		}
		next.ServeHTTP(w, r)
	})
}

func (m *Middleware) CORS(next http.Handler) http.Handler {
	allowed := make(map[string]bool)
	for _, o := range m.cfg.AllowedOrigins {
		allowed[strings.TrimSpace(o)] = true
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		if origin != "" && allowed[origin] {
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
			w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-CSRF-Token, X-Request-ID")
			w.Header().Set("Access-Control-Allow-Credentials", "true")
			w.Header().Set("Access-Control-Max-Age", "86400")
			w.Header().Set("Vary", "Origin")
		}
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (m *Middleware) Auth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := r.Header.Get("Authorization")
		if h == "" {
			writeError(w, http.StatusUnauthorized, "missing authorization header")
			return
		}
		parts := strings.SplitN(h, " ", 2)
		if len(parts) != 2 || parts[0] != "Bearer" {
			writeError(w, http.StatusUnauthorized, "invalid authorization format")
			return
		}
		claims, err := verifyJWT(m.cfg.JWTSecret, parts[1])
		if err != nil {
			writeError(w, http.StatusUnauthorized, "invalid or expired token")
			return
		}
		ctx := context.WithValue(r.Context(), ctxUserID, claims.UserID)
		ctx = context.WithValue(ctx, ctxEmail, claims.Email)
		ctx = context.WithValue(ctx, ctxRole, claims.Role)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func (m *Middleware) CSRFProtection(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet || r.Method == http.MethodHead || r.Method == http.MethodOptions {
			next.ServeHTTP(w, r)
			return
		}
		token := r.Header.Get("X-CSRF-Token")
		if token == "" || !m.store.ValidateCSRFToken(token) {
			writeError(w, http.StatusForbidden, "invalid or missing CSRF token")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (m *Middleware) RequireRole(role string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			userRole, _ := r.Context().Value(ctxRole).(string)
			if userRole != role {
				writeError(w, http.StatusForbidden, "insufficient permissions")
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// RateLimiter — simple in-memory, use Redis in production
type RateLimiter struct {
	mu       sync.Mutex
	requests map[string][]time.Time
	limit    int
	window   time.Duration
}

func NewRateLimiter(limit int, window time.Duration) *RateLimiter {
	rl := &RateLimiter{requests: make(map[string][]time.Time), limit: limit, window: window}
	go func() {
		for range time.Tick(5 * time.Minute) {
			rl.mu.Lock()
			now := time.Now()
			for k, times := range rl.requests {
				var valid []time.Time
				for _, t := range times {
					if now.Sub(t) < rl.window {
						valid = append(valid, t)
					}
				}
				if len(valid) == 0 {
					delete(rl.requests, k)
				} else {
					rl.requests[k] = valid
				}
			}
			rl.mu.Unlock()
		}
	}()
	return rl
}

func (rl *RateLimiter) Wrap(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ip := r.RemoteAddr
		if fwd := r.Header.Get("X-Forwarded-For"); fwd != "" {
			ip = strings.Split(fwd, ",")[0]
		}
		rl.mu.Lock()
		now := time.Now()
		var valid []time.Time
		for _, t := range rl.requests[ip] {
			if now.Sub(t) < rl.window {
				valid = append(valid, t)
			}
		}
		if len(valid) >= rl.limit {
			rl.mu.Unlock()
			w.Header().Set("Retry-After", fmt.Sprintf("%d", int(rl.window.Seconds())))
			writeError(w, http.StatusTooManyRequests, "rate limit exceeded")
			return
		}
		rl.requests[ip] = append(valid, now)
		rl.mu.Unlock()
		next.ServeHTTP(w, r)
	})
}

// RequestLogger logs requests
func RequestLogger(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rec := &statusRecorder{ResponseWriter: w, code: 200}
		next.ServeHTTP(rec, r)
		log.Printf("[%s] %d %s %s %v", time.Now().Format("15:04:05"), rec.code, r.Method, r.URL.Path, time.Since(start))
	})
}

type statusRecorder struct {
	http.ResponseWriter
	code int
}

func (sr *statusRecorder) WriteHeader(code int) { sr.code = code; sr.ResponseWriter.WriteHeader(code) }

// ===========================================================================
// Handlers
// ===========================================================================

type Handlers struct {
	cfg   *Config
	store *Store
}

func NewHandlers(cfg *Config, store *Store) *Handlers {
	return &Handlers{cfg: cfg, store: store}
}

func (h *Handlers) Health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, HealthResponse{
		Status: "healthy", Version: Version,
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Uptime:    time.Since(startTime).Round(time.Second).String(),
	})
}

func (h *Handlers) Ready(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
}

func (h *Handlers) Register(w http.ResponseWriter, r *http.Request) {
	var req RegisterRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.Email == "" || req.Password == "" || req.Name == "" {
		writeError(w, http.StatusBadRequest, "email, name and password are required")
		return
	}
	if len(req.Password) < 8 {
		writeError(w, http.StatusBadRequest, "password must be at least 8 characters")
		return
	}
	user, err := h.store.CreateUser(req.Email, req.Name, req.Password, "user")
	if err != nil {
		writeError(w, http.StatusConflict, err.Error())
		return
	}
	h.respondAuth(w, http.StatusCreated, user)
}

func (h *Handlers) Login(w http.ResponseWriter, r *http.Request) {
	var req LoginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	user, err := h.store.GetUserByEmail(req.Email)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "invalid credentials")
		return
	}
	if err := bcrypt.CompareHashAndPassword([]byte(user.Password), []byte(req.Password)); err != nil {
		writeError(w, http.StatusUnauthorized, "invalid credentials")
		return
	}
	h.respondAuth(w, http.StatusOK, user)
}

func (h *Handlers) RefreshToken(w http.ResponseWriter, r *http.Request) {
	var req struct {
		RefreshToken string `json:"refresh_token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	userID, ok := h.store.ValidateRefreshToken(req.RefreshToken)
	if !ok {
		writeError(w, http.StatusUnauthorized, "invalid refresh token")
		return
	}
	h.store.RevokeRefreshToken(req.RefreshToken)
	user, err := h.store.GetUserByID(userID)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "user not found")
		return
	}
	h.respondAuth(w, http.StatusOK, user)
}

func (h *Handlers) GetCurrentUser(w http.ResponseWriter, r *http.Request) {
	userID := r.Context().Value(ctxUserID).(string)
	user, err := h.store.GetUserByID(userID)
	if err != nil {
		writeError(w, http.StatusNotFound, "user not found")
		return
	}
	writeJSON(w, http.StatusOK, user)
}

func (h *Handlers) ListUsers(w http.ResponseWriter, _ *http.Request) {
	users := h.store.ListUsers()
	writeJSON(w, http.StatusOK, map[string]interface{}{"users": users, "total": len(users)})
}

func (h *Handlers) respondAuth(w http.ResponseWriter, status int, user *User) {
	accessToken, _ := createJWT(h.cfg.JWTSecret, JWTClaims{
		UserID: user.ID, Email: user.Email, Role: user.Role,
		Exp: time.Now().Add(15 * time.Minute).Unix(), Iat: time.Now().Unix(),
	})
	refreshToken := generateToken()
	h.store.StoreRefreshToken(refreshToken, user.ID)
	csrfToken := generateToken()
	h.store.StoreCSRFToken(csrfToken)
	writeJSON(w, status, AuthResponse{
		AccessToken: accessToken, RefreshToken: refreshToken,
		User: *user, CSRFToken: csrfToken,
	})
}

// ===========================================================================
// Response helpers
// ===========================================================================

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, APIError{Error: http.StatusText(status), Message: message, Code: status})
}

// ===========================================================================
// Main
// ===========================================================================

func main() {
	cfg := LoadConfig()
	store := NewStore()
	handlers := NewHandlers(cfg, store)
	mw := NewMiddleware(cfg, store)

	authRL := NewRateLimiter(10, time.Minute)
	apiRL := NewRateLimiter(100, time.Minute)

	mux := http.NewServeMux()

	// Public
	mux.HandleFunc("GET /health", handlers.Health)
	mux.HandleFunc("GET /ready", handlers.Ready)

	// Auth (rate limited)
	mux.Handle("POST /api/v1/auth/register", authRL.Wrap(http.HandlerFunc(handlers.Register)))
	mux.Handle("POST /api/v1/auth/login", authRL.Wrap(http.HandlerFunc(handlers.Login)))
	mux.Handle("POST /api/v1/auth/refresh", authRL.Wrap(http.HandlerFunc(handlers.RefreshToken)))

	// Protected
	protect := func(h http.HandlerFunc) http.Handler {
		return apiRL.Wrap(mw.Auth(mw.CSRFProtection(http.HandlerFunc(h))))
	}
	mux.Handle("GET /api/v1/users/me", protect(handlers.GetCurrentUser))
	mux.Handle("GET /api/v1/users", protect(mw.RequireRole("admin")(http.HandlerFunc(handlers.ListUsers)).ServeHTTP))

	// Apply global middleware
	var handler http.Handler = mux
	handler = mw.CORS(handler)
	handler = mw.SecurityHeaders(handler)
	handler = RequestLogger(handler)

	srv := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           handler,
		ReadTimeout:       10 * time.Second,
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       120 * time.Second,
		MaxHeaderBytes:    1 << 20,
	}

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		log.Printf("API server on :%s (env=%s, version=%s)", cfg.Port, cfg.Environment, Version)
		log.Printf("  CORS origins: %v", cfg.AllowedOrigins)
		log.Printf("  Demo user: admin@example.com / admin123")
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server error: %v", err)
		}
	}()

	<-quit
	log.Println("Shutting down...")
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Fatalf("Forced shutdown: %v", err)
	}
	log.Println("Server exited")
}
