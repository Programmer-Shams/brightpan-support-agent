"""Generate the importable n8n workflow JSON files in n8n/workflows/ (BUILD_SPEC step 4).

The JSON holds no secrets: API keys live in n8n credentials (created by deploy.py),
and deploy-time values use placeholders that deploy.py fills in:
  __CRED_<NAME>__        n8n credential ids
  __WF_<TOOL>__          sub-workflow ids
  __SUPABASE_URL__, __SHOPIFY_SHOP__, __SLACK_WEBHOOK_URL__

Code-node JavaScript lives in n8n/js/*.js (tested by n8n/js/test.mjs).

Workflows:
  tool-search-help-center  embed query (OpenAI) -> match_kb_chunks (Supabase), top 4
  tool-lookup-order        Shopify Admin GraphQL; details only if order number AND email match
  tool-escalate-to-human   verify email vs order -> row in Supabase `handoffs` -> Slack message
  agent-claude / agent-openai   webhook (header auth) -> AI Agent (3 tools, memory) -> log turn -> respond
"""
import json
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "workflows"
JS = HERE / "js"
SHOPIFY_API_VERSION = "2026-10"
TOP_K = 4
HTTP_TIMEOUT_MS = 15000
WEBHOOK_AUTH_HEADER = "X-Brightpan-Key"

MODELS = {
    "claude": {
        "label": "Claude Opus 5.5",
        "path": "brightpan-chat",
        "model_id": "claude-opus-5-5",
        "node": {
            "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic", "typeVersion": 1.6,
            "parameters": {
                "model": {"__rl": True, "mode": "id", "value": "claude-opus-5-5"},
                # Opus 5.5 rejects temperature and disabled thinking; low effort keeps replies fast.
                "options": {"maxTokensToSample": 4096, "thinkingMode": "adaptive", "effort": "low"},
            },
            "credentials": {"anthropicApi": {"id": "__CRED_ANTHROPIC__", "name": "Brightpan Anthropic"}},
        },
    },
    "openai": {
        "label": "OpenAI GPT-5.5",
        "path": "brightpan-chat-openai",
        "model_id": "gpt-5.5",
        "node": {
            "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi", "typeVersion": 1.3,
            "parameters": {
                "model": {"__rl": True, "mode": "id", "value": "gpt-5.5"},
                # GPT-5.5 only accepts the default temperature; low reasoning effort keeps replies fast.
                "options": {"reasoningEffort": "low"},
            },
            "credentials": {"openAiApi": {"id": "__CRED_OPENAI__", "name": "Brightpan OpenAI"}},
        },
    },
}

SUPABASE_CRED = {"supabaseApi": {"id": "__CRED_SUPABASE__", "name": "Brightpan Supabase"}}
OPENAI_CRED = {"openAiApi": {"id": "__CRED_OPENAI__", "name": "Brightpan OpenAI"}}
SHOPIFY_CRED = {"httpCustomAuth": {"id": "__CRED_SHOPIFY__", "name": "Brightpan Shopify client"}}
WEBHOOK_CRED = {"httpHeaderAuth": {"id": "__CRED_WEBHOOK__", "name": "Brightpan webhook key"}}
# Workflows that handle the short-lived Shopify access token keep no execution data,
# so the token never sits in n8n's execution history.
NO_EXECUTION_DATA = {"saveDataSuccessExecution": "none", "saveDataErrorExecution": "none"}


def js(name: str, **replace) -> str:
    text = (JS / f"{name}.js").read_text()
    for k, v in replace.items():
        text = text.replace(k, v)
    return text.strip()


def node(name, type_, version, params, pos, **extra):
    return {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"brightpan/{name}")), "name": name, "type": type_,
            "typeVersion": version, "position": pos, "parameters": params, **extra}


def code(name, source, pos, **extra):
    return node(name, "n8n-nodes-base.code", 2, {"jsCode": source}, pos, **extra)


def http(name, pos, url, body_expr, *, retry, auth=None, headers=None, **extra):
    """POST JSON. Retry only idempotent calls (reads); never writes such as inserts or Slack posts."""
    params = {"method": "POST", "url": url, "sendBody": True, "specifyBody": "json", "jsonBody": body_expr,
              "options": {"timeout": HTTP_TIMEOUT_MS}}
    if auth:
        params.update(auth)
    if headers:
        params["sendHeaders"] = True
        params["headerParameters"] = {"parameters": [{"name": k, "value": v} for k, v in headers.items()]}
    if retry:
        extra.update(retryOnFail=True, maxTries=3, waitBetweenTries=1000)
    return node(name, "n8n-nodes-base.httpRequest", 4.2, params, pos, **extra)


def supabase_auth():
    return {"authentication": "predefinedCredentialType", "nodeCredentialType": "supabaseApi"}


def trigger():
    return node("When called by agent", "n8n-nodes-base.executeWorkflowTrigger", 1.1,
                {"inputSource": "passthrough"}, [0, 0])


def chain(*names):
    return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]} for a, b in zip(names, names[1:])}


def workflow(name, nodes, connections, **settings):
    return {"name": name, "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1", "saveManualExecutions": True, **settings}}


def shopify_nodes(x, fields):
    """Client-credentials token + order search by name (the order number is digits only, see order_parse.js)."""
    token = node("Shopify token", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": "https://__SHOPIFY_SHOP__.myshopify.com/admin/oauth/access_token",
        "authentication": "genericCredentialType", "genericAuthType": "httpCustomAuth",
        "sendBody": True, "contentType": "form-urlencoded",
        "bodyParameters": {"parameters": [{"name": "grant_type", "value": "client_credentials"}]},
        "options": {"timeout": HTTP_TIMEOUT_MS},
    }, [x, 0], credentials=SHOPIFY_CRED, retryOnFail=True, maxTries=3, waitBetweenTries=1000)
    query = f"query($q: String!) {{ orders(first: 5, query: $q) {{ nodes {{ {fields} }} }} }}"
    find = http("Find order", [x + 220, 0],
                f"https://__SHOPIFY_SHOP__.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/graphql.json",
                "={{ JSON.stringify({ query: " + json.dumps(query) +
                ", variables: { q: 'name:#' + ($('Parse input').first().json.order_number || '0') } }) }}",
                retry=True, headers={"X-Shopify-Access-Token": "={{ $json.access_token }}"})
    return token, find


# ---------- tool: search_help_center ----------

def tool_search():
    embed = http("Embed query", [220, 0], "https://api.openai.com/v1/embeddings",
                 "={{ JSON.stringify({ model: 'text-embedding-3-small', input: String($json.query || '').slice(0, 2000) }) }}",
                 retry=True, auth={"authentication": "predefinedCredentialType", "nodeCredentialType": "openAiApi"},
                 credentials=OPENAI_CRED)
    match = http("Match articles", [440, 0], "__SUPABASE_URL__/rest/v1/rpc/match_kb_chunks",
                 f"={{{{ JSON.stringify({{ query_embedding: $json.data[0].embedding, match_count: {TOP_K} }}) }}}}",
                 retry=True, auth=supabase_auth(), credentials=SUPABASE_CRED, alwaysOutputData=True)
    fmt = code("Format results", js("search_format"), [660, 0])
    return workflow("Brightpan tool: search_help_center", [trigger(), embed, match, fmt],
                    chain("When called by agent", "Embed query", "Match articles", "Format results"))


# ---------- tool: lookup_order ----------

LOOKUP_FIELDS = ("name email processedAt cancelledAt displayFinancialStatus displayFulfillmentStatus "
                 "totalPriceSet { shopMoney { amount currencyCode } } "
                 "totalShippingPriceSet { shopMoney { amount currencyCode } } "
                 "customAttributes { key value } "
                 "lineItems(first: 20) { nodes { title quantity customAttributes { key value } "
                 "originalUnitPriceSet { shopMoney { amount currencyCode } } } }")


def tool_lookup():
    parse = code("Parse input", js("order_parse"), [220, 0])
    token, find = shopify_nodes(440, LOOKUP_FIELDS)
    result = code("Check email and format", js("lookup_result"), [880, 0])
    return workflow("Brightpan tool: lookup_order", [trigger(), parse, token, find, result],
                    chain("When called by agent", "Parse input", "Shopify token", "Find order",
                          "Check email and format"), **NO_EXECUTION_DATA)


# ---------- tool: escalate_to_human ----------

def tool_escalate(slack: bool):
    parse = code("Parse input", js("order_parse"), [220, 0])
    token, find = shopify_nodes(440, "name email")
    verify = code("Verify customer", js("escalate_verify"), [880, 0])
    save = http("Save handoff", [1100, 0], "__SUPABASE_URL__/rest/v1/handoffs", "={{ JSON.stringify($json.row) }}",
                retry=False, auth=supabase_auth(), credentials=SUPABASE_CRED,
                headers={"Prefer": "return=representation"})
    nodes = [trigger(), parse, token, find, verify, save]
    names = ["When called by agent", "Parse input", "Shopify token", "Find order", "Verify customer", "Save handoff"]
    if slack:
        nodes.append(http("Notify Slack", [1320, 0], "__SLACK_WEBHOOK_URL__",
                          "={{ JSON.stringify({ text: 'New Brightpan handoff #' + $json.id, blocks: [{ type: 'section', "
                          "text: { type: 'mrkdwn', text: ':rotating_light: *New Brightpan handoff #' + $json.id + '* — ' "
                          "+ $('Verify customer').first().json.slack_title } }].concat($('Verify customer').first().json.slack_blocks) }) }}",
                          retry=False, onError="continueRegularOutput"))
        names.append("Notify Slack")
    nodes.append(code("Confirm", js("escalate_confirm"), [1540, 0]))
    names.append("Confirm")
    return workflow("Brightpan tool: escalate_to_human", nodes, chain(*names), **NO_EXECUTION_DATA)


# ---------- main agent workflow ----------

TOOL_DEFS = {
    "search_help_center": {
        "wf": "__WF_SEARCH__",
        "description": "Search the Brightpan help center. Call this for every question about products, care, "
                       "shipping, returns, refunds, warranty, payments, discounts or any store policy. "
                       "Returns the top 4 articles with their id and exact title.",
        "inputs": {"query": ("string", "A short search query describing what the customer wants to know")},
    },
    "lookup_order": {
        "wf": "__WF_LOOKUP__",
        "description": "Look up one order. Requires BOTH the order number and the email used at checkout. "
                       "Returns details only when both match; otherwise returns NO_MATCH.",
        "inputs": {"order_number": ("string", "The order number the customer gave, digits only"),
                   "email": ("string", "The email address the customer gave")},
        "fixed": {"session_id": "={{ $('Prepare').first().json.session_id }}"},
    },
    "escalate_to_human": {
        "wf": "__WF_ESCALATE__",
        "description": "Hand the conversation to the human support team. Use for refunds, damaged/defective/wrong "
                       "items, warranty claims, order changes after the 1-hour window, complaints, chargeback or "
                       "legal threats, or when the customer asks for a person.",
        "inputs": {"reason": ("string", "One of: refund, damaged_or_wrong_item, warranty, order_change, complaint, "
                                        "chargeback_or_legal, customer_request, other"),
                   "summary": ("string", "2-3 factual sentences for the support agent"),
                   "customer_email": ("string", "Customer email if given, else empty"),
                   "order_number": ("string", "Order number if given, else empty")},
        "fixed": {"session_id": "={{ $('Prepare').first().json.session_id }}"},
    },
}


def tool_node(name, spec, pos):
    value = {field: f"={{{{ $fromAI('{field}', {json.dumps(desc)}, '{typ}') }}}}"
             for field, (typ, desc) in spec["inputs"].items()}
    value.update(spec.get("fixed", {}))
    schema = [{"id": f, "displayName": f, "required": False, "defaultMatch": False, "display": True,
               "canBeUsedToMatch": True, "type": "string", "removed": False} for f in value]
    return node(name, "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, {
        "description": spec["description"],
        "source": "database",
        "workflowId": {"__rl": True, "mode": "id", "value": spec["wf"]},
        "workflowInputs": {"mappingMode": "defineBelow", "value": value, "matchingColumns": [], "schema": schema,
                           "attemptToConvertTypes": False, "convertFieldsToString": False},
    }, pos)


LOG_FIELDS = ["session_id", "user_message", "tools_called", "article_ids_used", "article_ids_retrieved",
              "answer", "escalated", "latency_ms", "model", "error"]


def agent_workflow(key):
    m = MODELS[key]
    system = (HERE / "system_prompt.md").read_text().replace("{{TODAY}}", "{{ $('Prepare').first().json.today }}")
    log_body = "={{ JSON.stringify({ " + ", ".join(f"{f}: $json.log.{f}" for f in LOG_FIELDS) + " }) }}"
    model_node = f"Chat model ({m['label']})"
    nodes = [
        node("Webhook", "n8n-nodes-base.webhook", 2.1,
             {"httpMethod": "POST", "path": m["path"], "authentication": "headerAuth",
              "responseMode": "responseNode", "options": {}},
             [0, 0], webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, f"brightpan/webhook/{key}")),
             credentials=WEBHOOK_CRED),
        code("Prepare", js("prepare"), [220, 0], onError="continueErrorOutput"),
        node("Respond bad request", "n8n-nodes-base.respondToWebhook", 1.4,
             {"respondWith": "json",
              "responseBody": "={{ { error: 'Send JSON with a non-empty \"message\" string.' } }}",
              "options": {"responseCode": 400}}, [460, 200]),
        node("AI Agent", "@n8n/n8n-nodes-langchain.agent", 3.1, {
            "promptType": "define", "text": "={{ $json.message }}",
            "options": {"systemMessage": "=" + system, "maxIterations": 8,
                        "returnIntermediateSteps": True, "enableStreaming": False},
        }, [460, 0], onError="continueErrorOutput"),
        node(model_node, m["node"]["type"], m["node"]["typeVersion"], m["node"]["parameters"],
             [300, 260], credentials=m["node"]["credentials"]),
        node("Conversation memory", "@n8n/n8n-nodes-langchain.memoryBufferWindow", 1.4,
             {"sessionIdType": "customKey", "sessionKey": "={{ $('Prepare').first().json.session_id }}",
              "contextWindowLength": 10}, [460, 260]),
        tool_node("search_help_center", TOOL_DEFS["search_help_center"], [620, 260]),
        tool_node("lookup_order", TOOL_DEFS["lookup_order"], [780, 260]),
        tool_node("escalate_to_human", TOOL_DEFS["escalate_to_human"], [940, 260]),
        code("Build turn", js("build_turn", __MODEL_ID__=m["model_id"]), [760, -100], onError="continueErrorOutput"),
        http("Log turn", [980, -100], "__SUPABASE_URL__/rest/v1/conversations", log_body,
             retry=False, auth=supabase_auth(), credentials=SUPABASE_CRED, onError="continueRegularOutput"),
        node("Respond", "n8n-nodes-base.respondToWebhook", 1.4,
             {"respondWith": "json", "responseBody": "={{ $('Build turn').first().json.response }}", "options": {}},
             [1200, -100]),
        code("Error turn", js("error_turn", __MODEL_ID__=m["model_id"]), [980, 120]),
        http("Log error", [1200, 120], "__SUPABASE_URL__/rest/v1/conversations", log_body,
             retry=False, auth=supabase_auth(), credentials=SUPABASE_CRED, onError="continueRegularOutput"),
        http("Save error handoff", [1420, 120], "__SUPABASE_URL__/rest/v1/handoffs",
             "={{ JSON.stringify($('Error turn').first().json.handoff) }}",
             retry=False, auth=supabase_auth(), credentials=SUPABASE_CRED, onError="continueRegularOutput"),
        node("Respond error", "n8n-nodes-base.respondToWebhook", 1.4,
             {"respondWith": "json", "responseBody": "={{ $('Error turn').first().json.response }}", "options": {}},
             [1640, 120]),
    ]
    to = lambda name: [{"node": name, "type": "main", "index": 0}]  # noqa: E731
    conn = {
        "Webhook": {"main": [to("Prepare")]},
        "Prepare": {"main": [to("AI Agent"), to("Respond bad request")]},
        "AI Agent": {"main": [to("Build turn"), to("Error turn")]},
        "Build turn": {"main": [to("Log turn"), to("Error turn")]},
        **chain("Log turn", "Respond"),
        **chain("Error turn", "Log error", "Save error handoff", "Respond error"),
        model_node: {"ai_languageModel": [[{"node": "AI Agent", "type": "ai_languageModel", "index": 0}]]},
        "Conversation memory": {"ai_memory": [[{"node": "AI Agent", "type": "ai_memory", "index": 0}]]},
        **{t: {"ai_tool": [[{"node": "AI Agent", "type": "ai_tool", "index": 0}]]} for t in TOOL_DEFS},
    }
    return workflow(f"Brightpan support agent ({m['label']})", nodes, conn)


def build(slack: bool = True) -> dict:
    return {
        "tool-search-help-center": tool_search(),
        "tool-lookup-order": tool_lookup(),
        "tool-escalate-to-human": tool_escalate(slack),
        **{f"agent-{k}": agent_workflow(k) for k in MODELS},
    }


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, wf in build().items():
        (OUT / f"{name}.json").write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote n8n/workflows/{name}.json ({len(wf['nodes'])} nodes)")
