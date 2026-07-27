# Analysis job contract

## State machine

```text
queued -> running -> completed
                  -> failed -> queued (retry)
                  -> cancel_requested -> cancelled -> queued (retry)
queued -> cancelled
```

Terminal states are `completed`, `failed`, and `cancelled`. A completed job must have
an `AnalysisResult`; a failed job must have a structured `JobError`.

Progress is monotonic in `[0, 1]`. Stages are:

1. `prepare`
2. `tile_inference`
3. `merge`
4. `metrics`
5. `export`
6. `terminal`

Retry creates a new attempt number. It never overwrites artifacts from an earlier
completed attempt.

## Process boundary

- Process cha owns `AnalysisJobService`, SQLite and all state transitions.
- Worker process loads model, reads image, runs pipeline and writes a hidden staging directory.
- Worker sends only serializable progress/result/error messages through a queue.
- Worker never imports or updates Qt widgets and never writes job state into SQLite.
- Parent coalesces consecutive progress messages before persistence/UI notification.
- Default capacity is one worker; `dispatch_queued()` respects `max_workers`.

The worker uses multiprocessing `spawn` for consistent Windows, macOS and Linux
behavior. A worker that exits without a terminal message becomes retryable error
`worker_exited`.

## Cancellation and restart

Cancellation uses a process-safe event checked before image decode, every tile and
artifact publication. A cancellation observed before atomic rename cannot produce a
completed artifact directory.

After app restart, `recover_interrupted()` converts `running` and
`cancel_requested` jobs to retryable `worker_interrupted` failures and removes hidden
staging directories. Queued jobs remain queued and can be resumed with
`dispatch_queued()`.

## Error codes

- `pipeline_execution_error`: invalid/unreadable input or pipeline contract failure.
- `model_manifest_error`, `model_unavailable`, `inference_runtime_error`: AI boundary errors.
- `job_io_error`: worker-level operating system I/O failure.
- `job_out_of_memory`: simulated/detected OOM; retryable.
- `worker_start_failed`, `worker_exited`, `worker_interrupted`: process lifecycle errors.
- `worker_unhandled_error`: unexpected exception with type and traceback in context.
