import pytest
import subprocess
import sys
import os

def run_cli(*args, db_path):
    cmd = [sys.executable, "memory_cli.py", "--db", str(db_path)] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__))
    )
    return result

def test_cli_lifecycle_and_stale_query(tmp_path):
    db_path = tmp_path / "cli_test.db"

    # 1. Record job discovery with domain and candidate_id
    res = run_cli(
        "record",
        "-a", "app_cli_1",
        "-t", "job_discovered",
        "-c", "Stripe",
        "-d", "stripe.com",
        "--candidate-id", "sdn9300",
        "-r", "Backend Engineer",
        db_path=db_path
    )
    assert res.returncode == 0
    assert "DISCOVERED" in res.stdout

    # 2. Check status
    res = run_cli("status", "app_cli_1", db_path=db_path)
    assert res.returncode == 0
    assert "Stripe" in res.stdout
    assert "stripe.com" in res.stdout
    assert "sdn9300" in res.stdout
    assert "DISCOVERED" in res.stdout

    # 3. Record outreach
    res = run_cli("record", "-a", "app_cli_1", "-t", "outreach_sent", db_path=db_path)
    assert res.returncode == 0
    assert "OUTREACHED" in res.stdout

    # 4. Check history
    res = run_cli("history", "app_cli_1", db_path=db_path)
    assert res.returncode == 0
    assert "job_discovered" in res.stdout
    assert "outreach_sent" in res.stdout

    # 5. List applications (all & by candidate)
    res = run_cli("list", db_path=db_path)
    assert res.returncode == 0
    assert "app_cli_1" in res.stdout
    assert "Stripe" in res.stdout

    res_cand = run_cli("list", "--candidate-id", "sdn9300", db_path=db_path)
    assert res_cand.returncode == 0
    assert "app_cli_1" in res_cand.stdout

    # 6. Check cooldown CLI before rejection -> CLEAR
    res_cd1 = run_cli("cooldown", "--domain", "stripe.com", db_path=db_path)
    assert res_cd1.returncode == 0
    assert "CLEAR" in res_cd1.stdout

    # 7. Record rejection
    res_rej = run_cli(
        "record",
        "-a", "app_cli_1",
        "-t", "response_classified",
        "-d", "stripe.com",
        "--intent", "hard_rejection",
        db_path=db_path
    )
    assert res_rej.returncode == 0
    assert "REJECTED" in res_rej.stdout

    # 8. Check cooldown CLI after rejection -> BLOCKED
    res_cd2 = run_cli("cooldown", "--domain", "stripe.com", db_path=db_path)
    assert res_cd2.returncode == 0
    assert "BLOCKED" in res_cd2.stdout

    # 9. Check stale query
    res = run_cli("stale", "--days", "0", db_path=db_path)
    assert res.returncode == 0

    # 10. Rebuild command
    res = run_cli("rebuild", db_path=db_path)
    assert res.returncode == 0
    assert "Rebuild complete!" in res.stdout
