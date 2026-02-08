import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/auth'
import { api, sanitize } from '@/lib/api'

interface HealthData {
  status: string
  version: string
  timestamp: string
  uptime: string
}

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user)

  const { data: health, isLoading } = useQuery<HealthData>({
    queryKey: ['health'],
    queryFn: () => api.get('/../../health'), // health está na raiz, não em /api/v1
    refetchInterval: 30000,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-600 mt-1">
          Bem-vindo, <span dangerouslySetInnerHTML={{ __html: sanitize(user?.name || '') }} />
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* User Card */}
        <div className="bg-white rounded-xl border p-6 shadow-sm">
          <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider">Usuário</h3>
          <div className="mt-4 space-y-2">
            <p className="text-lg font-semibold">{user?.name}</p>
            <p className="text-sm text-gray-600">{user?.email}</p>
            <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-medium ${
              user?.role === 'admin' ? 'bg-purple-100 text-purple-800' : 'bg-blue-100 text-blue-800'
            }`}>
              {user?.role}
            </span>
          </div>
        </div>

        {/* API Status */}
        <div className="bg-white rounded-xl border p-6 shadow-sm">
          <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider">API Status</h3>
          <div className="mt-4">
            {isLoading ? (
              <div className="animate-pulse h-6 bg-gray-200 rounded w-20" />
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <span className={`h-3 w-3 rounded-full ${health?.status === 'healthy' ? 'bg-green-500' : 'bg-red-500'}`} />
                  <span className="text-lg font-semibold capitalize">{health?.status || 'unknown'}</span>
                </div>
                <p className="text-sm text-gray-500 mt-2">Versão: {health?.version}</p>
                <p className="text-sm text-gray-500">Uptime: {health?.uptime}</p>
              </>
            )}
          </div>
        </div>

        {/* Security */}
        <div className="bg-white rounded-xl border p-6 shadow-sm">
          <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider">Segurança</h3>
          <div className="mt-4 space-y-2">
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-green-500" />
              <span className="text-sm">CSRF Protection</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-green-500" />
              <span className="text-sm">XSS Sanitization</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-green-500" />
              <span className="text-sm">Same-Origin Policy</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-green-500" />
              <span className="text-sm">JWT in Memory Only</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-green-500" />
              <span className="text-sm">Rate Limiting</span>
            </div>
          </div>
        </div>
      </div>

      {/* Info */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-6">
        <h3 className="font-medium text-blue-900">Sobre este Template</h3>
        <p className="text-sm text-blue-700 mt-2">
          Este é um template monorepo com múltiplos backends (Go, Python, C#) e frontends (React, Angular, mobile).
          O frontend web se comunica com a API Go via proxy reverso (mesmo domínio), eliminando CORS.
          Tokens JWT são mantidos em memória (Zustand), nunca em localStorage/sessionStorage.
          Todas as requests de escrita incluem CSRF token. Conteúdo dinâmico é sanitizado contra XSS via DOMPurify.
        </p>
      </div>
    </div>
  )
}
