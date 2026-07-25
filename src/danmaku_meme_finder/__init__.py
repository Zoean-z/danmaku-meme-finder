"""Local Douyu danmaku candidate-meme finder."""

import warnings

# This project does not use Pydantic plugins. Some global Python installations
# contain an incompatible optional logfire plugin; avoid its non-actionable
# startup warning without suppressing validation errors from this package.
warnings.filterwarnings(
    "ignore",
    message=r"ImportError while loading the `logfire-plugin` Pydantic plugin.*",
    category=UserWarning,
    module=r"pydantic\.plugin\._schema_validator",
)

__version__ = "0.1.0"
