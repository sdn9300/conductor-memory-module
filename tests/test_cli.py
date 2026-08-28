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

    # 1. Record job discovery
    res = run_cli("record", "-a", "app_cli_1", "-t", "job_discovered", "-c", "Stripe", "-r", "Backend Engineer", db_path=db_path)
    assert res.returncode == 0
    assert "DISCOVERED" in res.stdout

    # 2. Check status
    res = run_cli("status", "app_cli_1", db_path=db_path)
    assert res.returncode == 0
    assert "Stripe" in res.stdout
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

    # 5. List applications
    res = run_cli("list", db_path=db_path)
    assert res.returncode == 0
    assert "app_cli_1" in res.stdout
    assert "Stripe" in res.stdout

    # 6. Check stale query (with days=0 to match immediate activity)
    res = run_cli("stale", "--days", "0", db_path=db_path)
    assert res.returncode == 0
    assert "app_cli_1" in res.stdout

    # 7. Rebuild command
    res = run_cli("rebuild", db_path=db_path)
    assert res.returncode == 0
    assert "Rebuild complete!" in res.stdout
