"""python -m framework.observability 入口（委托给 dashboard.main）。"""
import sys
from .dashboard import main

if __name__ == "__main__":
    sys.exit(main())