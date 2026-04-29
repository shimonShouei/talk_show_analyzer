#!/bin/bash
# Monitor the E2E SLURM job

JOB_ID="${1:-17265960}"
LOG_FILE="slurm_logs/job_${JOB_ID}.out"

echo "Monitoring E2E test job #$JOB_ID"
echo "=================================="
echo ""

# Check status
echo "Status:"
squeue -j $JOB_ID -o "%.18i %.9P %.8j %.8u %.8T %.10M %.9l %N" || echo "Job not found in queue (may have completed)"
echo ""

# Show logs if available
if [ -f "$LOG_FILE" ]; then
    echo "Latest log output:"
    echo "=================================="
    tail -30 "$LOG_FILE"
    echo ""
    echo "To see full log: tail -f $LOG_FILE"
else
    echo "Log file not yet created: $LOG_FILE"
fi

echo ""
echo "Commands:"
echo "  • Watch logs live:     tail -f $LOG_FILE"
echo "  • Cancel job:          scancel $JOB_ID"
echo "  • View all details:    squeue -j $JOB_ID --all"
echo "  • Check GPU:           sstat -j $JOB_ID --format=AveCPU,AvePages,AveRSS,AveVMSize,MaxRSS,MaxVMSize,MaxPages,AvePages"
