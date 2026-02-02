"""
Módulo Landing Page - Deploy de página de teste para verificar acesso público.

Cria um deployment com uma landing page futurista temática Raijin.
"""

from __future__ import annotations

import subprocess
import typer

from raijin_server.utils import ExecutionContext, run_cmd, write_file
from pathlib import Path

NAMESPACE = "landing"

# HTML da landing page com animações de raios e tema futurista
LANDING_HTML = '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Raijin Server</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;900&family=Rajdhani:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            min-height: 100vh;
            background: linear-gradient(135deg, #0a0a1a 0%, #0d1b2a 25%, #1b263b 50%, #0d1b2a 75%, #0a0a1a 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            font-family: 'Rajdhani', sans-serif;
            overflow: hidden;
            position: relative;
        }

        /* Grid de fundo futurista */
        .grid-bg {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-image: 
                linear-gradient(rgba(0, 150, 255, 0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 150, 255, 0.03) 1px, transparent 1px);
            background-size: 50px 50px;
            animation: gridMove 20s linear infinite;
            z-index: 0;
        }

        @keyframes gridMove {
            0% { transform: perspective(500px) rotateX(60deg) translateY(0); }
            100% { transform: perspective(500px) rotateX(60deg) translateY(50px); }
        }

        /* Container de raios */
        .lightning-container {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 1;
        }

        /* Raio SVG animado */
        .lightning {
            position: absolute;
            opacity: 0;
            filter: drop-shadow(0 0 10px #00d4ff) drop-shadow(0 0 30px #0096ff) drop-shadow(0 0 60px #0066ff);
        }

        .lightning path {
            stroke: #00d4ff;
            stroke-width: 3;
            fill: none;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        .lightning.flash {
            animation: lightningFlash 0.3s ease-out forwards;
        }

        @keyframes lightningFlash {
            0% { opacity: 0; }
            10% { opacity: 1; }
            20% { opacity: 0.3; }
            30% { opacity: 1; }
            50% { opacity: 0.5; }
            70% { opacity: 0.8; }
            100% { opacity: 0; }
        }

        /* Partículas elétricas */
        .particle {
            position: absolute;
            width: 4px;
            height: 4px;
            background: #00d4ff;
            border-radius: 50%;
            box-shadow: 0 0 10px #00d4ff, 0 0 20px #0096ff, 0 0 40px #0066ff;
            animation: particleFloat 3s ease-in-out infinite;
        }

        @keyframes particleFloat {
            0%, 100% { transform: translateY(0) scale(1); opacity: 0.3; }
            50% { transform: translateY(-20px) scale(1.5); opacity: 1; }
        }

        /* Ondas de energia */
        .energy-wave {
            position: fixed;
            border: 2px solid rgba(0, 212, 255, 0.1);
            border-radius: 50%;
            animation: waveExpand 4s ease-out infinite;
        }

        @keyframes waveExpand {
            0% { width: 0; height: 0; opacity: 0.8; }
            100% { width: 200vmax; height: 200vmax; opacity: 0; }
        }

        /* Container principal */
        .container {
            text-align: center;
            z-index: 10;
            padding: 2rem;
            position: relative;
        }

        /* Logo/Símbolo */
        .logo-container {
            margin-bottom: 2rem;
            position: relative;
        }

        .logo {
            width: 150px;
            height: 150px;
            position: relative;
            margin: 0 auto;
        }

        .logo-circle {
            position: absolute;
            width: 100%;
            height: 100%;
            border: 3px solid transparent;
            border-top-color: #00d4ff;
            border-radius: 50%;
            animation: spin 3s linear infinite;
        }

        .logo-circle:nth-child(2) {
            width: 80%;
            height: 80%;
            top: 10%;
            left: 10%;
            border-top-color: #0096ff;
            animation-duration: 2s;
            animation-direction: reverse;
        }

        .logo-circle:nth-child(3) {
            width: 60%;
            height: 60%;
            top: 20%;
            left: 20%;
            border-top-color: #0066ff;
            animation-duration: 1.5s;
        }

        @keyframes spin {
            100% { transform: rotate(360deg); }
        }

        .logo-icon {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 3rem;
            color: #00d4ff;
            text-shadow: 0 0 20px #00d4ff, 0 0 40px #0096ff;
        }

        /* Título */
        h1 {
            font-family: 'Orbitron', sans-serif;
            font-size: clamp(2.5rem, 8vw, 5rem);
            font-weight: 900;
            background: linear-gradient(135deg, #00d4ff 0%, #0096ff 50%, #0066ff 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            text-transform: uppercase;
            letter-spacing: 0.3em;
            margin-bottom: 0.5rem;
            position: relative;
            animation: titleGlow 2s ease-in-out infinite alternate;
        }

        @keyframes titleGlow {
            0% { filter: drop-shadow(0 0 10px rgba(0, 212, 255, 0.5)); }
            100% { filter: drop-shadow(0 0 30px rgba(0, 212, 255, 0.8)); }
        }

        /* Subtítulo */
        .subtitle {
            font-size: clamp(1rem, 3vw, 1.5rem);
            color: rgba(255, 255, 255, 0.7);
            text-transform: uppercase;
            letter-spacing: 0.5em;
            margin-bottom: 3rem;
            font-weight: 300;
        }

        /* Mensagem de boas-vindas */
        .welcome {
            font-family: 'Orbitron', sans-serif;
            font-size: clamp(1.5rem, 4vw, 2.5rem);
            color: #fff;
            margin-bottom: 1rem;
            opacity: 0;
            animation: fadeInUp 1s ease-out 0.5s forwards;
        }

        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Linha decorativa */
        .divider {
            width: 200px;
            height: 2px;
            background: linear-gradient(90deg, transparent, #00d4ff, transparent);
            margin: 2rem auto;
            position: relative;
        }

        .divider::before {
            content: '';
            position: absolute;
            width: 10px;
            height: 10px;
            background: #00d4ff;
            border-radius: 50%;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            box-shadow: 0 0 20px #00d4ff;
            animation: pulse 2s ease-in-out infinite;
        }

        @keyframes pulse {
            0%, 100% { transform: translate(-50%, -50%) scale(1); }
            50% { transform: translate(-50%, -50%) scale(1.5); }
        }

        /* Status */
        .status {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.75rem 2rem;
            background: rgba(0, 212, 255, 0.1);
            border: 1px solid rgba(0, 212, 255, 0.3);
            border-radius: 50px;
            color: #00d4ff;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.2em;
            opacity: 0;
            animation: fadeInUp 1s ease-out 1s forwards;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            background: #00ff88;
            border-radius: 50%;
            box-shadow: 0 0 10px #00ff88;
            animation: statusPulse 1.5s ease-in-out infinite;
        }

        @keyframes statusPulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }

        /* Info do servidor */
        .server-info {
            margin-top: 3rem;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1.5rem;
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
            opacity: 0;
            animation: fadeInUp 1s ease-out 1.5s forwards;
        }

        .info-card {
            background: rgba(0, 20, 40, 0.6);
            border: 1px solid rgba(0, 212, 255, 0.2);
            border-radius: 10px;
            padding: 1.5rem;
            transition: all 0.3s ease;
        }

        .info-card:hover {
            border-color: rgba(0, 212, 255, 0.5);
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0, 212, 255, 0.2);
        }

        .info-label {
            font-size: 0.7rem;
            color: rgba(255, 255, 255, 0.5);
            text-transform: uppercase;
            letter-spacing: 0.2em;
            margin-bottom: 0.5rem;
        }

        .info-value {
            font-family: 'Orbitron', sans-serif;
            font-size: 1.2rem;
            color: #00d4ff;
        }

        /* Footer */
        .footer {
            position: fixed;
            bottom: 2rem;
            left: 50%;
            transform: translateX(-50%);
            color: rgba(255, 255, 255, 0.3);
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.3em;
        }

        /* Scanline effect */
        .scanline {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(
                transparent 50%,
                rgba(0, 0, 0, 0.02) 50%
            );
            background-size: 100% 4px;
            pointer-events: none;
            z-index: 100;
        }

        /* Corner decorations */
        .corner {
            position: fixed;
            width: 100px;
            height: 100px;
            border: 2px solid rgba(0, 212, 255, 0.3);
            pointer-events: none;
        }

        .corner-tl { top: 20px; left: 20px; border-right: none; border-bottom: none; }
        .corner-tr { top: 20px; right: 20px; border-left: none; border-bottom: none; }
        .corner-bl { bottom: 20px; left: 20px; border-right: none; border-top: none; }
        .corner-br { bottom: 20px; right: 20px; border-left: none; border-top: none; }
    </style>
</head>
<body>
    <div class="scanline"></div>
    <div class="grid-bg"></div>
    
    <div class="corner corner-tl"></div>
    <div class="corner corner-tr"></div>
    <div class="corner corner-bl"></div>
    <div class="corner corner-br"></div>
    
    <div class="lightning-container" id="lightningContainer"></div>
    
    <div class="container">
        <div class="logo-container">
            <div class="logo">
                <div class="logo-circle"></div>
                <div class="logo-circle"></div>
                <div class="logo-circle"></div>
                <div class="logo-icon">⚡</div>
            </div>
        </div>
        
        <h1>Raijin</h1>
        <p class="subtitle">Infrastructure Automation</p>
        
        <div class="divider"></div>
        
        <p class="welcome">Seja Bem-Vindo</p>
        
        <div class="status">
            <span class="status-dot"></span>
            Sistema Operacional
        </div>
        
        <div class="server-info">
            <div class="info-card">
                <div class="info-label">Kubernetes</div>
                <div class="info-value">Online</div>
            </div>
            <div class="info-card">
                <div class="info-label">Cluster</div>
                <div class="info-value">Asgard</div>
            </div>
            <div class="info-card">
                <div class="info-label">Domínio</div>
                <div class="info-value">.internal</div>
            </div>
        </div>
    </div>
    
    <div class="footer">Powered by Raijin Server</div>

    <script>
        // Criar partículas flutuantes
        function createParticles() {
            const container = document.body;
            for (let i = 0; i < 30; i++) {
                const particle = document.createElement('div');
                particle.className = 'particle';
                particle.style.left = Math.random() * 100 + 'vw';
                particle.style.top = Math.random() * 100 + 'vh';
                particle.style.animationDelay = Math.random() * 3 + 's';
                particle.style.animationDuration = (2 + Math.random() * 2) + 's';
                container.appendChild(particle);
            }
        }

        // Criar ondas de energia
        function createWaves() {
            const container = document.body;
            setInterval(() => {
                const wave = document.createElement('div');
                wave.className = 'energy-wave';
                wave.style.left = '50%';
                wave.style.top = '50%';
                wave.style.transform = 'translate(-50%, -50%)';
                container.appendChild(wave);
                setTimeout(() => wave.remove(), 4000);
            }, 3000);
        }

        // Gerar raio SVG
        function generateLightningPath() {
            const points = [];
            let x = 0;
            let y = 0;
            const segments = 8 + Math.floor(Math.random() * 6);
            
            for (let i = 0; i < segments; i++) {
                points.push({ x, y });
                x += 20 + Math.random() * 40;
                y += 30 + Math.random() * 50;
                if (Math.random() > 0.7) {
                    x -= 30 + Math.random() * 20;
                }
            }
            
            let path = `M ${points[0].x} ${points[0].y}`;
            for (let i = 1; i < points.length; i++) {
                path += ` L ${points[i].x} ${points[i].y}`;
            }
            
            return { path, width: Math.max(...points.map(p => p.x)) + 50, height: y + 50 };
        }

        // Criar e animar raios
        function createLightning() {
            const container = document.getElementById('lightningContainer');
            
            const lightning = generateLightningPath();
            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('class', 'lightning');
            svg.setAttribute('width', lightning.width);
            svg.setAttribute('height', lightning.height);
            svg.style.left = Math.random() * (window.innerWidth - lightning.width) + 'px';
            svg.style.top = Math.random() * (window.innerHeight - lightning.height) * 0.5 + 'px';
            
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('d', lightning.path);
            svg.appendChild(path);
            
            container.appendChild(svg);
            
            // Trigger animation
            requestAnimationFrame(() => {
                svg.classList.add('flash');
            });
            
            // Remove after animation
            setTimeout(() => svg.remove(), 500);
        }

        // Inicializar
        createParticles();
        createWaves();
        
        // Raios aleatórios
        setInterval(() => {
            if (Math.random() > 0.6) {
                createLightning();
                // Às vezes criar múltiplos raios
                if (Math.random() > 0.7) {
                    setTimeout(createLightning, 50);
                }
            }
        }, 800);
        
        // Raio inicial dramático
        setTimeout(() => {
            createLightning();
            setTimeout(createLightning, 100);
            setTimeout(createLightning, 200);
        }, 500);
    </script>
</body>
</html>
'''


def run(ctx: ExecutionContext) -> None:
    """Executa o deploy da landing page de teste."""
    typer.echo("\n" + "=" * 60)
    typer.echo("RAIJIN LANDING PAGE - Teste de Acesso Público")
    typer.echo("=" * 60 + "\n")

    if not typer.confirm("Fazer deploy da landing page de teste?", default=True):
        typer.echo("Operação cancelada.")
        return

    # Criar namespace
    run_cmd(
        ["kubectl", "create", "namespace", NAMESPACE],
        ctx,
        check=False,
    )

    # Criar ConfigMap com o HTML
    configmap_yaml = f'''apiVersion: v1
kind: ConfigMap
metadata:
  name: landing-html
  namespace: {NAMESPACE}
data:
  index.html: |
{_indent_html(LANDING_HTML, 4)}
'''

    # Deployment + Service + IngressRoute
    deployment_yaml = f'''---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: landing
  namespace: {NAMESPACE}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: landing
  template:
    metadata:
      labels:
        app: landing
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
        ports:
        - containerPort: 80
        volumeMounts:
        - name: html
          mountPath: /usr/share/nginx/html
        resources:
          requests:
            memory: "32Mi"
            cpu: "10m"
          limits:
            memory: "64Mi"
            cpu: "50m"
      volumes:
      - name: html
        configMap:
          name: landing-html
      tolerations:
      - key: node-role.kubernetes.io/control-plane
        operator: Exists
        effect: NoSchedule
      - key: node-role.kubernetes.io/master
        operator: Exists
        effect: NoSchedule
---
apiVersion: v1
kind: Service
metadata:
  name: landing
  namespace: {NAMESPACE}
spec:
  type: NodePort
  selector:
    app: landing
  ports:
  - port: 80
    targetPort: 80
    nodePort: 30000
---
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: landing
  namespace: {NAMESPACE}
spec:
  entryPoints:
    - web
    - websecure
  routes:
  - match: Host(`raijin.asgard.internal`) || Host(`www.asgard.internal`) || PathPrefix(`/`)
    kind: Rule
    services:
    - name: landing
      port: 80
'''

    # Escrever e aplicar ConfigMap
    configmap_path = Path("/tmp/raijin-landing-configmap.yaml")
    write_file(configmap_path, configmap_yaml, ctx)
    run_cmd(["kubectl", "apply", "-f", str(configmap_path)], ctx)

    # Escrever e aplicar Deployment/Service/IngressRoute
    deployment_path = Path("/tmp/raijin-landing-deployment.yaml")
    write_file(deployment_path, deployment_yaml, ctx)
    run_cmd(["kubectl", "apply", "-f", str(deployment_path)], ctx)

    # Aguardar pods ficarem ready
    typer.echo("\nAguardando pods ficarem ready...")
    if not ctx.dry_run:
        run_cmd(
            ["kubectl", "rollout", "status", "deployment/landing", "-n", NAMESPACE, "--timeout=60s"],
            ctx,
            check=False,
        )

    _show_access_info()


def _indent_html(html: str, spaces: int) -> str:
    """Indenta o HTML para o ConfigMap YAML."""
    indent = " " * spaces
    return "\n".join(indent + line for line in html.split("\n"))


def _show_access_info() -> None:
    """Mostra informações de acesso."""
    typer.echo("\n" + "=" * 60)
    typer.echo("LANDING PAGE DEPLOYED!")
    typer.echo("=" * 60)
    typer.echo("""
📦 Acesso via NodePort:
   http://<node-ip>:30000

📦 Acesso via DNS interno:
   http://raijin.asgard.internal (requer internal-dns + VPN)

📦 Acesso via Traefik (porta 80/443):
   http://<node-ip>:30080

🔧 Para testar acesso público:
   1. Configure port-forward no roteador: 80 → <node-ip>:30080
   2. Configure DDNS ou IP fixo
   3. Acesse via IP público ou domínio

📝 Comandos úteis:
   kubectl get pods -n landing
   kubectl logs -n landing -l app=landing
""")


def uninstall(ctx: ExecutionContext) -> None:
    """Remove a landing page."""
    typer.echo("Removendo landing page...")
    run_cmd(["kubectl", "delete", "namespace", NAMESPACE, "--ignore-not-found"], ctx)
    typer.echo("Landing page removida.")
