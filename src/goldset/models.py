from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()

# timeout is load-bearing: judge calls are synchronous, so an unbounded
# request blocks the event loop and freezes the whole run (observed
# 2026-08-02 during an upstream API incident — every worker stalled at
# its next judge call). Bounded here, and run_test additionally runs
# evaluations off the loop thread.
HAIKU = ChatAnthropic(
    model="claude-haiku-4-5",
    temperature=0,
    max_tokens=8_192,
    timeout=60.0,
    max_retries=2,
)
