from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ingest

app = FastAPI(title="Coogaih API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

if __name__ == "__main__":
    N_DRAWS = 2000  # single draws are anecdotes; the table reports a distribution

    def persona(rng, conf_mu, acc_prob, n=20):
        out = []
        for _ in range(n):
            c = float(np.clip(rng.normal(conf_mu, 0.06), 0, 1))
            r = rng.random()
            o = "correct" if r < acc_prob else ("partial" if r < acc_prob + 0.1 else "incorrect")
            out.append((c, o))
        return out

    def band(seed, conf_mu, acc_prob, drift=0.0, n=20):
        # Per-persona seed: each row is reproducible in isolation, and rows
        # sharing a seed are the SAME learner (so the drift row is comparable).
        rng = np.random.default_rng(seed)
        vals = [risk_score(persona(rng, conf_mu, acc_prob, n), drift)[0] for _ in range(N_DRAWS)]
        if all(v is None for v in vals):
            return None, None, None
        a = np.array(vals, dtype=float)
        return (round(float(np.median(a)), 3),
                round(float(np.percentile(a, 10)), 3),
                round(float(np.percentile(a, 90)), 3))

    rows = [
        ("well-calibrated (conf ~ accuracy)", 101, 0.70, 0.70, 0.0, 20),
        ("UNDERconfident (humble, right)",    102, 0.35, 0.90, 0.0, 20),
        ("mildly overconfident",              103, 0.75, 0.55, 0.0, 20),
        ("confidently-wrong",                 104, 0.85, 0.20, 0.0, 20),
        ("confidently-wrong + drifting (.8)", 104, 0.85, 0.20, 0.8, 20),  # same seed = same learner
        ("< N_MIN assessable logs",           105, 0.85, 0.20, 0.0,  4),
    ]

    print(f"{'learner pattern':<36} {'risk':>6}  {'p10-p90':>14}")
    print("-" * 60)
    for name, seed, cm, ap, dr, n in rows:
        m, lo, hi = band(seed, cm, ap, dr, n)
        shown = "NULL" if m is None else m
        rng_s = "--" if m is None else f"{lo} - {hi}"
        print(f"{name:<36} {str(shown):>6}  {rng_s:>14}")
