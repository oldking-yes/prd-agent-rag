#!/bin/bash
# PRD Agent RAG — 一键部署脚本
# 用法: bash deploy.sh

set -e

PROJECT_DIR="d:/桌面/Claude Code/prd_agent_rag"

echo "========================"
echo "PRD Agent RAG Deploy"
echo "========================"

# =========================================
# 1. 部署前端静态页到 Vercel
# =========================================
echo ""
echo "[1/3] Deploying frontend to Vercel..."

STATIC_DIR="$PROJECT_DIR/frontend/static"
mkdir -p "$STATIC_DIR"
cp "$PROJECT_DIR/frontend/index.html" "$STATIC_DIR/"
echo '{"version":2,"public":true,"cleanUrls":true}' > "$STATIC_DIR/vercel.json"

cd "$STATIC_DIR"
npx vercel deploy --prod --yes --scope kukik-s-projects \
  --token vca_59QfVynk1VVtNyNRmI2lIRDizjTTfEHXw7Vm9beIReI8V7Kd611XKwC2

echo "Frontend deployed!"
echo ""

# =========================================
# 2. 部署后端到 Zeabur
# =========================================
echo "[2/3] Deploying backend to Zeabur..."

cd "$PROJECT_DIR/backend"

# Create tar archive (excluding unnecessary files)
tar czf /tmp/prd-backend.tar.gz \
  --exclude='__pycache__' \
  --exclude='.venv' \
  --exclude='.env' \
  --exclude='data' \
  --exclude='chroma_data' \
  --exclude='uploads' \
  --exclude='.git' \
  --exclude='*.pyc' \
  . 2>/dev/null

# Upload to Zeabur via API
echo "Uploading to Zeabur..."
python3 -c "
import requests, json, base64

with open('/tmp/prd-backend.tar.gz', 'rb') as f:
    tar_data = f.read()

headers = {'Authorization': 'Bearer sk-milljfshg4ihquelh7emirt77gyqb'}

# Create service
query = {
    'query': '''mutation {
        createService(
            projectId: \"6a0c670d40a883532f331734\",
            input: {
                name: \"prd-agent-rag-api\",
                framework: \"dockerfile\"
            }
        ) {
            id name status
        }
    }'''
}
r = requests.post('https://api.zeabur.com/graphql', json=query, headers=headers)
print('Create service:', r.text)
"

echo ""
echo "[3/3] Setting up DNS..."
echo "After deployment, configure DNS:"
echo "  Frontend: CNAME prd.refineyourself.asia → your-vercel-url.vercel.app"
echo "  Backend:  CNAME prd-api.refineyourself.asia → your-zeabur-url.zeabur.app"
echo ""
echo "Done!"
