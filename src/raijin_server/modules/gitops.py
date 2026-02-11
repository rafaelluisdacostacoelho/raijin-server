"""
Modulo para configuracao automatizada de CI/CD e GitOps.
Detecta tipo de aplicacao e configura pipeline completa.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import typer

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from raijin_server.utils import ExecutionContext, run_cmd


def _detect_project_type(repo_path: Path) -> Tuple[str, Dict[str, any]]:
    """
    Detecta tipo de projeto e retorna configuracao apropriada.
    
    Returns:
        (tipo, config_dict)
    """
    # Python
    if (repo_path / "requirements.txt").exists() or (repo_path / "pyproject.toml").exists():
        dockerfile = repo_path / "Dockerfile"
        if not dockerfile.exists():
            return ("python-api", {
                "runtime": "python:3.11-slim",
                "port": 8000,
                "health_endpoint": "/health"
            })
    
    # Node.js
    if (repo_path / "package.json").exists():
        with open(repo_path / "package.json") as f:
            pkg = json.load(f)
        
        # Detectar framework
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        
        if "next" in deps:
            return ("nextjs", {
                "runtime": "node:20-alpine",
                "port": 3000,
                "build_cmd": "npm run build",
                "start_cmd": "npm start"
            })
        elif "react" in deps or "vite" in deps:
            return ("spa-react", {
                "runtime": "node:20-alpine",
                "port": 3000,
                "build_cmd": "npm run build",
                "serve": "nginx"
            })
        elif "express" in deps or "fastify" in deps:
            return ("nodejs-api", {
                "runtime": "node:20-alpine",
                "port": 3000,
                "health_endpoint": "/health"
            })
    
    # Go
    if (repo_path / "go.mod").exists():
        return ("golang", {
            "runtime": "golang:1.21-alpine",
            "port": 8080,
            "health_endpoint": "/health"
        })
    
    # Supabase (custom deployment)
    if (repo_path / "supabase").exists() or "supabase" in repo_path.name.lower():
        return ("supabase-custom", {
            "port": 8000,
            "requires": ["postgresql", "kong"]
        })
    
    # Static site
    if (repo_path / "index.html").exists():
        return ("static", {
            "runtime": "nginx:alpine",
            "port": 80
        })
    
    return ("unknown", {})


def _generate_dockerfile(project_type: str, config: Dict, repo_path: Path) -> str:
    """Gera Dockerfile baseado no tipo de projeto."""
    
    templates = {
        "python-api": """FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE {port}

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{port}"]
""",
        
        "nodejs-api": """FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY . .

EXPOSE {port}

CMD ["node", "index.js"]
""",
        
        "nextjs": """FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE {port}

CMD ["node", "server.js"]
""",
        
        "spa-react": """FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
""",
        
        "static": """FROM nginx:alpine

COPY . /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
"""
    }
    
    template = templates.get(project_type, templates["static"])
    return template.format(**config)


def _generate_k8s_manifests(
    app_name: str,
    namespace: str,
    domain: str,
    image: str,
    port: int,
    replicas: int = 2
) -> Dict[str, str]:
    """Gera manifests Kubernetes completos."""
    
    manifests = {}
    
    # Namespace
    manifests["namespace.yaml"] = f"""apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
"""
    
    # Deployment
    manifests["deployment.yaml"] = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_name}
  namespace: {namespace}
  labels:
    app: {app_name}
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      app: {app_name}
  template:
    metadata:
      labels:
        app: {app_name}
    spec:
      containers:
      - name: {app_name}
        image: {image}
        ports:
        - containerPort: {port}
          name: http
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi
        livenessProbe:
          httpGet:
            path: /health
            port: {port}
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: {port}
          initialDelaySeconds: 10
          periodSeconds: 5
"""
    
    # Service
    manifests["service.yaml"] = f"""apiVersion: v1
kind: Service
metadata:
  name: {app_name}
  namespace: {namespace}
  labels:
    app: {app_name}
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: {port}
    protocol: TCP
  selector:
    app: {app_name}
"""
    
    # Ingress
    manifests["ingress.yaml"] = f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {app_name}-ingress
  namespace: {namespace}
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
  tls:
  - hosts:
    - {domain}
    secretName: {app_name}-tls
  rules:
  - host: {domain}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: {app_name}
            port:
              number: 80
"""
    
    # HPA
    manifests["hpa.yaml"] = f"""apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {app_name}-hpa
  namespace: {namespace}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {app_name}
  minReplicas: {replicas}
  maxReplicas: {replicas * 2}
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
"""
    
    return manifests


def _generate_github_actions(
    app_name: str,
    harbor_url: str,
    image_name: str,
    k8s_namespace: str
) -> str:
    """Gera GitHub Actions workflow."""
    
    return f"""name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  HARBOR_URL: {harbor_url}
  IMAGE_NAME: {image_name}
  K8S_NAMESPACE: {k8s_namespace}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3
    
    - name: Login to Harbor
      uses: docker/login-action@v3
      with:
        registry: ${{{{ env.HARBOR_URL }}}}
        username: ${{{{ secrets.HARBOR_USERNAME }}}}
        password: ${{{{ secrets.HARBOR_PASSWORD }}}}
    
    - name: Extract metadata
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: ${{{{ env.HARBOR_URL }}}}/${{{{ env.IMAGE_NAME }}}}
        tags: |
          type=ref,event=branch
          type=ref,event=pr
          type=sha,prefix={{{{branch}}}}-
          type=raw,value=latest,enable={{{{is_default_branch}}}}
    
    - name: Build and push
      uses: docker/build-push-action@v5
      with:
        context: .
        push: true
        tags: ${{{{ steps.meta.outputs.tags }}}}
        labels: ${{{{ steps.meta.outputs.labels }}}}
        cache-from: type=gha
        cache-to: type=gha,mode=max
    
    - name: Update ArgoCD (if main branch)
      if: github.ref == 'refs/heads/main'
      run: |
        # ArgoCD auto-sync ira detectar mudanca automaticamente
        echo "Image pushed: ${{{{ steps.meta.outputs.tags }}}}"
        echo "ArgoCD will sync automatically"

  deploy-staging:
    needs: build-and-push
    if: github.ref == 'refs/heads/develop'
    runs-on: ubuntu-latest
    steps:
    - name: Deploy to Staging
      run: |
        echo "Deploying to staging environment"
        # Add staging deployment logic here

  deploy-production:
    needs: build-and-push
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://{app_name}.cryptidnest.com
    steps:
    - name: Deploy to Production
      run: |
        echo "Deploying to production environment"
        # ArgoCD handles deployment automatically
"""


def _generate_argocd_application(
    app_name: str,
    namespace: str,
    repo_url: str,
    manifests_path: str = "k8s"
) -> str:
    """Gera ArgoCD Application manifest."""
    
    return f"""apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {app_name}
  namespace: argocd
  finalizers:
  - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: {repo_url}
    targetRevision: main
    path: {manifests_path}
  destination:
    server: https://kubernetes.default.svc
    namespace: {namespace}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
      allowEmpty: false
    syncOptions:
    - CreateNamespace=true
    - PrunePropagationPolicy=foreground
    - PruneLast=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
  revisionHistoryLimit: 10
"""


def setup_gitops(ctx: ExecutionContext) -> None:
    """
    Configura pipeline CI/CD completa para um repositorio.
    Detecta tipo de aplicacao e gera toda configuracao necessaria.
    """
    typer.secho("\n🚀  Setup GitOps/CI/CD Automatizado\n", fg=typer.colors.CYAN, bold=True)
    
    # Inputs
    repo_url = typer.prompt("URL do repositorio GitHub (https://github.com/user/repo)")
    app_name = typer.prompt("Nome da aplicacao", default=repo_url.split("/")[-1].replace(".git", ""))
    namespace = typer.prompt("Namespace Kubernetes", default=app_name)
    domain = typer.prompt("Dominio (ex: app.cryptidnest.com)", default=f"{app_name}.cryptidnest.com")
    
    harbor_url = typer.prompt("Harbor Registry URL", default="harbor.cryptidnest.com")
    harbor_project = typer.prompt("Harbor Project", default="library")
    
    replicas = typer.prompt("Numero de replicas", default=2, type=int)
    
    # Clone repositorio temporariamente para analise
    typer.echo("\n📥 Clonando repositorio para analise...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_path = Path(tmpdir) / "repo"
        
        # Configurar Git para não pedir senha interativamente
        import subprocess
        env_vars = os.environ.copy()
        env_vars['GIT_TERMINAL_PROMPT'] = '0'
        env_vars['GIT_ASKPASS'] = 'true'
        
        result = subprocess.run(
            ["git", "clone", "--depth=1", repo_url, str(clone_path)],
            env=env_vars,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            typer.secho(f"✗ Falha ao clonar repositorio: {result.stderr}", fg=typer.colors.RED)
            raise typer.Exit(1)
        
        # Detectar tipo de projeto
        typer.echo("🔍 Detectando tipo de projeto...")
        project_type, config = _detect_project_type(clone_path)
        typer.secho(f"  ✓ Tipo detectado: {project_type}", fg=typer.colors.GREEN)
        
        # Gerar estrutura
        k8s_dir = clone_path / "k8s"
        k8s_dir.mkdir(exist_ok=True)
        
        github_dir = clone_path / ".github" / "workflows"
        github_dir.mkdir(parents=True, exist_ok=True)
        
        # Gerar Dockerfile se nao existir
        dockerfile_path = clone_path / "Dockerfile"
        if not dockerfile_path.exists():
            typer.echo("📝 Gerando Dockerfile...")
            port = config.get("port", 8000)
            dockerfile_content = _generate_dockerfile(project_type, config, clone_path)
            dockerfile_path.write_text(dockerfile_content)
            typer.secho(f"  ✓ Dockerfile criado", fg=typer.colors.GREEN)
        
        # Gerar Kubernetes manifests
        typer.echo("📝 Gerando manifests Kubernetes...")
        image = f"{harbor_url}/{harbor_project}/{app_name}:latest"
        port = config.get("port", 8000)
        
        manifests = _generate_k8s_manifests(
            app_name=app_name,
            namespace=namespace,
            domain=domain,
            image=image,
            port=port,
            replicas=replicas
        )
        
        for filename, content in manifests.items():
            (k8s_dir / filename).write_text(content)
        
        typer.secho(f"  ✓ {len(manifests)} manifests criados em k8s/", fg=typer.colors.GREEN)
        
        # Gerar GitHub Actions workflow
        typer.echo("📝 Gerando GitHub Actions workflow...")
        workflow_content = _generate_github_actions(
            app_name=app_name,
            harbor_url=harbor_url,
            image_name=f"{harbor_project}/{app_name}",
            k8s_namespace=namespace
        )
        (github_dir / "cicd.yml").write_text(workflow_content)
        typer.secho("  ✓ Workflow criado em .github/workflows/cicd.yml", fg=typer.colors.GREEN)
        
        # Gerar ArgoCD Application
        typer.echo("📝 Gerando ArgoCD Application...")
        argocd_content = _generate_argocd_application(
            app_name=app_name,
            namespace=namespace,
            repo_url=repo_url
        )
        (k8s_dir / "argocd-application.yaml").write_text(argocd_content)
        typer.secho("  ✓ ArgoCD Application criado", fg=typer.colors.GREEN)
        
        # Gerar README
        readme_content = f"""# {app_name} - GitOps CI/CD

Configuracao automatica gerada por raijin-server.

## Estrutura

```
├── k8s/                          # Kubernetes manifests
│   ├── namespace.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   ├── hpa.yaml
│   └── argocd-application.yaml
├── .github/
│   └── workflows/
│       └── cicd.yml              # GitHub Actions
└── Dockerfile
```

## Setup

### 1. Configurar Secrets no GitHub

```bash
# Settings → Secrets and variables → Actions → New repository secret

HARBOR_USERNAME=<harbor-username>
HARBOR_PASSWORD=<harbor-password>
```

### 2. Deploy ArgoCD Application

```bash
kubectl apply -f k8s/argocd-application.yaml
```

### 3. Push para main branch

```bash
git add .
git commit -m "Add GitOps CI/CD configuration"
git push origin main
```

## Pipeline

```
Git Push → GitHub Actions → Build Docker → Push to Harbor → ArgoCD Sync → Deploy to K8s
```

## Acesso

- **URL**: https://{domain}
- **Namespace**: {namespace}
- **Replicas**: {replicas}

## Monitoramento

```bash
# Ver pods
kubectl get pods -n {namespace}

# Ver logs
kubectl logs -n {namespace} -l app={app_name} -f

# Ver status ArgoCD
kubectl get application {app_name} -n argocd
```
"""
        (clone_path / "GITOPS_README.md").write_text(readme_content)
        
        # Commit e push (se confirmado)
        typer.echo("\n📦 Arquivos gerados:")
        typer.echo("  • k8s/*.yaml (manifests Kubernetes)")
        typer.echo("  • .github/workflows/cicd.yml (GitHub Actions)")
        typer.echo("  • Dockerfile (se não existia)")
        typer.echo("  • GITOPS_README.md (documentação)")
        
        # Verificar se stdin é interativo ou aceitar input do pipe
        import sys
        if not sys.stdin.isatty():
            # Não-interativo: ler resposta do stdin ou assumir sim
            try:
                response = input("\n💾 Commitar e fazer push das mudanças? [Y/n]: ").strip().lower()
                confirm = response in ('', 'y', 'yes', 's', 'sim')
            except EOFError:
                confirm = True  # Default para sim quando não há input
        else:
            # Interativo: usar typer.confirm
            confirm = typer.confirm("\n💾 Commitar e fazer push das mudanças?", default=True)
        
        if confirm:
            # Configurar git user se necessário
            run_cmd(["git", "config", "user.email", "raijin-server@cryptidnest.com"], ctx, cwd=str(clone_path), check=False)
            run_cmd(["git", "config", "user.name", "Raijin Server"], ctx, cwd=str(clone_path), check=False)
            
            run_cmd(["git", "add", "."], ctx, cwd=str(clone_path))
            run_cmd(
                ["git", "commit", "-m", "Add GitOps CI/CD configuration via raijin-server"],
                ctx,
                cwd=str(clone_path),
                check=False
            )
            
            result = run_cmd(
                ["git", "push", "origin", "main"],
                ctx,
                cwd=str(clone_path),
                check=False
            )
            
            if result.returncode == 0:
                typer.secho("\n✓ Mudanças commitadas e pushed!", fg=typer.colors.GREEN)
            else:
                typer.secho("\n⚠ Falha no push. Verifique permissoes do repositorio.", fg=typer.colors.YELLOW)
    
    # Aplicar ArgoCD Application
    if not sys.stdin.isatty():
        try:
            response = input("\n🚀 Aplicar ArgoCD Application agora? [Y/n]: ").strip().lower()
            confirm_argocd = response in ('', 'y', 'yes', 's', 'sim')
        except EOFError:
            confirm_argocd = True
    else:
        confirm_argocd = typer.confirm("\n🚀 Aplicar ArgoCD Application agora?", default=True)
    
    if confirm_argocd:
        typer.echo("\nAplicando ArgoCD Application...")
        
        argocd_manifest = _generate_argocd_application(app_name, namespace, repo_url)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(argocd_manifest)
            manifest_file = f.name
        
        try:
            result = run_cmd(["kubectl", "apply", "-f", manifest_file], ctx, check=False)
            
            if result.returncode == 0:
                typer.secho(f"\n✓ ArgoCD Application '{app_name}' criado!", fg=typer.colors.GREEN)
                typer.echo(f"\n🌐 Sua aplicacao estara disponivel em: https://{domain}")
                typer.echo("\n📊 Monitorar deploy:")
                typer.echo(f"   kubectl get application {app_name} -n argocd -w")
                typer.echo(f"   kubectl get pods -n {namespace} -w")
            else:
                typer.secho("\n✗ Falha ao criar ArgoCD Application", fg=typer.colors.RED)
        finally:
            os.unlink(manifest_file)
    
    typer.secho("\n✅ GitOps CI/CD configurado com sucesso!", fg=typer.colors.GREEN, bold=True)
    typer.echo("\n📖 Proximo passo:")
    typer.echo("   1. Configure secrets no GitHub (HARBOR_USERNAME, HARBOR_PASSWORD)")
    typer.echo("   2. Push para branch main para triggerar pipeline")
    typer.echo("   3. ArgoCD ira fazer deploy automaticamente")


def run(ctx: ExecutionContext) -> None:
    """Funcao run padrao."""
    setup_gitops(ctx)


def uninstall(ctx: ExecutionContext) -> None:
    """Remove configuracao GitOps/ArgoCD."""
    app_name = typer.prompt("Nome da aplicacao para remover")
    
    # Remove ArgoCD Application
    result = run_cmd(
        ["kubectl", "delete", "application", app_name, "-n", "argocd"],
        ctx,
        check=False
    )
    
    if result.returncode == 0:
        typer.secho(f"✓ ArgoCD Application '{app_name}' removido.", fg=typer.colors.GREEN)
    else:
        typer.secho(f"✗ Falha ao remover Application.", fg=typer.colors.RED)
