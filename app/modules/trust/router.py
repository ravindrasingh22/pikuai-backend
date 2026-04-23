from fastapi import APIRouter

from app.shared.envelope import envelope

router = APIRouter()


@router.get("/benchmark-summary")
def benchmark_summary() -> dict[str, object]:
    return envelope(
        {
            "version": "benchmark-2026-04",
            "metrics": [
                {"label": "Blocked dangerous prompts", "value": "98%", "source": "internal_eval"},
                {"label": "Age-fit answer quality", "value": "92%", "source": "internal_eval"},
                {"label": "Parent review clarity", "value": "95%", "source": "internal_eval"},
                {"label": "Unsafe output rate", "value": "0.8%", "source": "internal_eval"},
            ],
        }
    )
