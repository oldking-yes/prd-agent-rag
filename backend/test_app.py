from fastapi import FastAPI, APIRouter

app = FastAPI()
router = APIRouter()

@router.get("/api/v1/health")
async def health():
    return {"status": "healthy"}

app.include_router(router)
