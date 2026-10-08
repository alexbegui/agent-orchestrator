import asyncio
import pytest
from app.services.runner_service import RunnerService


@pytest.mark.asyncio
async def test_runner_execute_output_streaming(tmp_path):
    runner = RunnerService()
    task_id = "test-exec-1"
    
    # Simple python one-liner to simulate agent output
    cmd = ["py", "-3", "-c", "print('Line 1'); print('Line 2')"]
    
    output_lines = []
    async for line in runner.execute_command(task_id, cmd, cwd=str(tmp_path)):
        output_lines.append(line.strip())
        
    assert "Line 1" in output_lines
    assert "Line 2" in output_lines
    assert task_id not in runner.active_processes


@pytest.mark.asyncio
async def test_runner_stop_process(tmp_path):
    runner = RunnerService()
    task_id = "test-stop-1"
    
    # Process that sleeps
    cmd = ["py", "-3", "-c", "import time; time.sleep(15)"]
    
    # Start execution in background task
    async def run_in_bg():
        async for _ in runner.execute_command(task_id, cmd, cwd=str(tmp_path)):
            pass

    bg_task = asyncio.create_task(run_in_bg())
    
    # Wait 0.5s for process to start
    await asyncio.sleep(0.5)
    assert task_id in runner.active_processes
    
    # Stop the task
    stopped = runner.stop_task(task_id)
    assert stopped is True
    
    # Clean up bg task
    try:
        await asyncio.wait_for(bg_task, timeout=2.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    assert task_id not in runner.active_processes
