"""Central, non-secret application constants."""

API_V1_PREFIX = "/api/v1"
REQUEST_ID_HEADER = "X-Request-ID"
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100

USER_ROLES = frozenset({"admin", "architect", "developer", "viewer"})
SUPPORTED_SOURCE_EXTENSIONS = frozenset(
    {".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".php", ".cs", ".go", ".rs", ".vue"}
)
