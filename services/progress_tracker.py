# services/progress_tracker.py
"""Thread-safe progress tracking for ML inference and clustering operations."""


class ProgressTracker:
    """Encapsulates mutable progress state for inference and clustering."""

    @staticmethod
    def create_inference_dict() -> dict:
        """Return a fresh inference progress dictionary."""
        return {
            "ml": "",
            "value_count": 0,
            "done": [],
            "ml_progress": None,
            "in_progress": None,
            "elapsed_time": 0,
            "is_multi": False,
            "is_abort": False
        }

    @staticmethod
    def create_clustering_dict() -> dict:
        """Return a fresh clustering progress dictionary."""
        return {}

    @staticmethod
    def reset_clustering_dict(d: dict) -> None:
        """Reset an existing clustering progress dict in-place."""
        d.update({
            "total": 0,
            "completed": [],
            "in_progress": None,
            "elapsed_time": 0,
            "metadata": None
        })
