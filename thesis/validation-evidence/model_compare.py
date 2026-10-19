"""Compare validator judge models against the actual execution outcome of a stored suite."""
import asyncio, json, os, re, sys, time
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")
from sqlalchemy import select, desc
from app.database import AsyncSessionLocal
from app.models import TestSuite, TestRunExecution, TestRun
from app.validation import service, static_checks
from app.validation.judge import judge_suite
from app.validation.findings import static_score

MODELS = [m for m in (os.getenv("CMP_MODELS") or "gpt-4o-mini,gpt-4o,gpt-4.1-mini,gpt-4.1").split(",") if m]
RUNS = int(os.getenv("CMP_RUNS", "2"))
OUT = sys.argv[1] if len(sys.argv) > 1 else "model_compare.json"

def words(s): return set(re.findall(r"[a-z0-9]+", (s or "").lower()))

async def main():
    async with AsyncSessionLocal() as db:
        # latest finished execution that has per-scenario rows
        q = await db.execute(select(TestRunExecution).where(TestRunExecution.total_count > 0, TestRunExecution.status.in_(["passed", "failed", "error"]), TestRunExecution.suite_id.isnot(None)).order_by(desc(TestRunExecution.started_at)).limit(20))
        execution = None; rows = []
        for ex in q.scalars().all():
            r = (await db.execute(select(TestRun).where(TestRun.execution_id == ex.id))).scalars().all()
            if r: execution, rows = ex, r; break
        assert execution, "no execution with scenario rows"
        suite = (await db.execute(select(TestSuite).where(TestSuite.id == execution.suite_id))).scalar_one()
        actual = {r.scenario_name: r.status for r in rows}
        texts, dom = await service.suite_context(db, suite)
        static = static_checks.check_suite_code(suite.code, framework=suite.framework, mode=suite.mode, url=suite.url, gherkin_texts=texts, dom_elements=dom or None)
        result = {"suite": {"id": str(suite.id), "framework": suite.framework, "version": suite.version, "mode": suite.mode, "lines": len(suite.code.splitlines())},
                  "execution": {"id": str(execution.id), "mode": execution.mode, "passed": execution.passed_count, "failed": execution.failed_count, "total": execution.total_count, "at": str(execution.finished_at or execution.started_at)},
                  "actual": actual, "static_score": static_score(static), "static_findings": [(f.severity, f.title) for f in static], "models": {}}
        print("suite", suite.framework, "v", suite.version, "| execution", execution.mode, execution.passed_count, "/", execution.total_count)
        for name, st in actual.items(): print("   actual", st, name)

        for model in MODELS:
            os.environ["VALIDATOR_MODEL"] = model
            runs = []
            for i in range(RUNS):
                t0 = time.perf_counter()
                try:
                    j = await judge_suite(code=suite.code, framework=suite.framework, mode=suite.mode, url=suite.url, gherkin_texts=texts, dom_elements=dom or None, static_findings=static)
                except Exception as e:
                    runs.append({"error": f"{type(e).__name__}: {str(e)[:160]}"}); print(model, "ERROR", e); continue
                dur = time.perf_counter() - t0
                # match predictions to actual rows by test name, then by title words
                matched = []; correct = 0; uncertain = 0
                for sc in j["scenarios"]:
                    key = None
                    tn = sc.get("test_name") or ""
                    if tn in actual: key = tn
                    else:
                        tw = words(sc["title"]) | words(tn.replace("_", " "))
                        best = max(actual, key=lambda n: len(words(n.replace("_", " ")) & tw) / max(1, len(words(n.replace("_", " ")))), default=None)
                        if best and len(words(best.replace("_", " ")) & tw) / max(1, len(words(best.replace("_", " ")))) >= 0.5: key = best
                    if not key: continue
                    act_pass = actual[key] == "passed"
                    if sc["predicted"] == "uncertain": uncertain += 1
                    ok = (sc["predicted"] == "pass") == act_pass and sc["predicted"] != "uncertain"
                    correct += ok
                    matched.append({"title": sc["title"], "test": key, "predicted": sc["predicted"], "confidence": sc["confidence"], "actual": actual[key], "correct": ok})
                scoring = service.compute_score(static, j)
                pred_rate = round(100 * sum(1 for s in j["scenarios"] if s["predicted"] == "pass") / max(1, len(j["scenarios"])))
                runs.append({"duration_s": round(dur, 1), "pass_probability": j["pass_probability"], "score": scoring["score"], "verdict": scoring["verdict"], "predicted_pass_rate": pred_rate, "matched": len(matched), "correct": correct, "uncertain": uncertain, "accuracy": round(100 * correct / len(matched)) if matched else None, "findings": [(f.severity, f.title) for f in j["findings"]], "scenarios": matched})
                print(f"{model} run{i+1}: score {scoring['score']} prob {j['pass_probability']} pred-rate {pred_rate}% acc {runs[-1]['accuracy']}% ({correct}/{len(matched)}, uncertain {uncertain}) findings {len(j['findings'])} {dur:.1f}s")
            result["models"][model] = runs
        json.dump(result, open(OUT, "w"), indent=1)
        print("saved", OUT)

asyncio.run(main())
