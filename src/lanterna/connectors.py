"""The connector catalog (Connectors → Browse): ready-made connectors and a search of the public MCP Registry.

The ready-made list holds connectors made by the services themselves. Each was checked on 8 November 2026: the
address answers, Lanterna can register itself for the browser sign-in and the sign-in page opens (or the
connector needs no sign-in). Services that only let apps they approved sign in are listed too, with why they
can't be connected and what works instead, so nobody searches in vain.

The registry (registry.modelcontextprotocol.io) lists thousands more, made by anyone: Lanterna shows who made
each one and warns when it isn't the service itself.
"""
from __future__ import annotations

import re
import urllib.parse

import httpx

from . import __version__

REGISTRY = "https://registry.modelcontextprotocol.io/v0/servers"

# (id, name, maker, category, address, sign-in, what it does)
_READY = [
    ("notion", "Notion", "Notion", "productivity", "https://mcp.notion.com/mcp", "oauth",
     "Search, read, create and update pages and databases in your Notion workspace."),
    ("linear", "Linear", "Linear", "productivity", "https://mcp.linear.app/mcp", "oauth",
     "Find, create and update issues, projects and comments in Linear."),
    ("atlassian", "Atlassian (Jira, Confluence)", "Atlassian", "productivity", "https://mcp.atlassian.com/v1/mcp", "oauth",
     "Search and update Jira issues and Confluence pages."),
    ("asana", "Asana", "Asana", "productivity", "https://mcp.asana.com/mcp", "oauth",
     "Work with tasks, projects and goals in Asana."),
    ("monday", "monday.com", "monday.com", "productivity", "https://mcp.monday.com/mcp", "oauth",
     "Read and update boards, items and updates on monday.com."),
    ("clickup", "ClickUp", "ClickUp", "productivity", "https://mcp.clickup.com/mcp", "oauth",
     "Search, create and update tasks, docs and lists in ClickUp."),
    ("todoist", "Todoist", "Doist", "productivity", "https://ai.todoist.net/mcp", "oauth",
     "Add, find and complete your Todoist tasks and projects."),
    ("airtable", "Airtable", "Airtable", "productivity", "https://mcp.airtable.com/mcp", "oauth",
     "Read and change records, tables and bases in Airtable."),
    ("coda", "Coda", "Coda", "productivity", "https://coda.io/apis/mcp", "oauth",
     "Read and edit Coda docs, tables and pages."),
    ("miro", "Miro", "Miro", "design", "https://mcp.miro.com/", "oauth",
     "Read boards and create diagrams, notes and frames in Miro."),
    ("canva", "Canva", "Canva", "design", "https://mcp.canva.com/mcp", "oauth",
     "Search, create, autofill and export Canva designs."),
    ("gamma", "Gamma", "Gamma", "design", "https://mcp.gamma.app/mcp", "oauth",
     "Make presentations, documents and web pages with Gamma."),
    ("lucid", "Lucid", "Lucid Software", "design", "https://mcp.lucid.app/mcp", "oauth",
     "Find and create Lucidchart and Lucidspark diagrams."),
    ("mermaid", "Mermaid Chart", "Mermaid", "design", "https://mcp.mermaidchart.com/mcp", "oauth",
     "Make and save diagrams written in Mermaid."),
    ("excalidraw", "Excalidraw", "Excalidraw", "design", "https://mcp.excalidraw.com/mcp", "open",
     "Draw hand-drawn style diagrams and sketches."),
    ("cloudinary", "Cloudinary", "Cloudinary", "design", "https://asset-management.mcp.cloudinary.com/mcp", "oauth",
     "Upload, find and transform images and videos in Cloudinary."),
    ("dropbox", "Dropbox", "Dropbox", "files", "https://mcp.dropbox.com/mcp", "oauth",
     "Search and read files and folders in your Dropbox."),
    ("egnyte", "Egnyte", "Egnyte", "files", "https://mcp-server.egnyte.com/mcp", "oauth",
     "Search and read files kept in Egnyte."),
    ("lumin", "Lumin", "Lumin", "files", "https://mcp.luminpdf.com/mcp", "oauth",
     "Work with PDFs and send documents for signing with Lumin."),
    ("readwise", "Readwise", "Readwise", "files", "https://mcp2.readwise.io/mcp", "oauth",
     "Search your highlights and saved articles in Readwise and Reader."),
    ("granola", "Granola", "Granola", "communication", "https://mcp.granola.ai/mcp", "oauth",
     "Search your meeting notes and transcripts in Granola."),
    ("fireflies", "Fireflies", "Fireflies.ai", "communication", "https://api.fireflies.ai/mcp", "oauth",
     "Find meeting transcripts, summaries and action items."),
    ("intercom", "Intercom", "Intercom", "communication", "https://mcp.intercom.com/mcp", "oauth",
     "Look up customer conversations, contacts and tickets in Intercom."),
    ("cal", "Cal.com", "Cal.com", "communication", "https://mcp.cal.com/mcp", "oauth",
     "See and book meetings in your Cal.com calendar."),
    ("github-builtin", "GitHub", "GitHub", "development", "", "builtin:github",
     "Read your repositories and save files there, after you confirm."),
    ("gitlab", "GitLab", "GitLab", "development", "https://gitlab.com/api/v4/mcp", "oauth",
     "Work with GitLab projects, issues and merge requests."),
    ("sentry", "Sentry", "Sentry", "development", "https://mcp.sentry.dev/mcp", "oauth",
     "Look into errors, issues and releases tracked in Sentry."),
    ("vercel", "Vercel", "Vercel", "development", "https://mcp.vercel.com", "oauth",
     "Check deployments, projects and logs on Vercel."),
    ("netlify", "Netlify", "Netlify", "development", "https://netlify-mcp.netlify.app/mcp", "oauth",
     "Create, deploy and manage Netlify sites."),
    ("cloudflare", "Cloudflare", "Cloudflare", "development", "https://bindings.mcp.cloudflare.com/mcp", "oauth",
     "Manage Workers, KV, R2 and D1 in your Cloudflare account."),
    ("cloudflare-obs", "Cloudflare Observability", "Cloudflare", "development", "https://observability.mcp.cloudflare.com/mcp", "oauth",
     "Read logs and analytics of your Cloudflare Workers."),
    ("cloudflare-docs", "Cloudflare Docs", "Cloudflare", "development", "https://docs.mcp.cloudflare.com/mcp", "open",
     "Search Cloudflare's documentation."),
    ("supabase", "Supabase", "Supabase", "development", "https://mcp.supabase.com/mcp", "oauth",
     "Manage Supabase projects, tables and SQL."),
    ("neon", "Neon", "Neon", "development", "https://mcp.neon.tech/mcp", "oauth",
     "Create and query Neon Postgres databases."),
    ("prisma", "Prisma Postgres", "Prisma", "development", "https://mcp.prisma.io/mcp", "oauth",
     "Create and manage Prisma Postgres databases."),
    ("stytch", "Stytch", "Stytch", "development", "https://mcp.stytch.dev/mcp", "oauth",
     "Manage Stytch projects and sign-in settings."),
    ("launchdarkly", "LaunchDarkly", "LaunchDarkly", "development", "https://mcp.launchdarkly.com/mcp", "oauth",
     "Create and change feature flags in LaunchDarkly."),
    ("jam", "Jam", "Jam", "development", "https://mcp.jam.dev/mcp", "oauth",
     "Read bug reports with screenshots, logs and network requests from Jam."),
    ("context7", "Context7", "Upstash", "development", "https://mcp.context7.com/mcp", "open",
     "Up-to-date documentation and code examples for libraries."),
    ("huggingface", "Hugging Face", "Hugging Face", "development", "https://huggingface.co/mcp", "open",
     "Search models, datasets, papers and Spaces on Hugging Face."),
    ("mslearn", "Microsoft Learn", "Microsoft", "development", "https://learn.microsoft.com/api/mcp", "open",
     "Search Microsoft's official documentation."),
    ("aws-knowledge", "AWS Knowledge", "Amazon Web Services", "development", "https://knowledge-mcp.global.api.aws", "open",
     "Search AWS documentation, guides and announcements."),
    ("socket", "Socket", "Socket", "development", "https://mcp.socket.dev/", "open",
     "Check open-source packages for security problems."),
    ("posthog", "PostHog", "PostHog", "data", "https://mcp.posthog.com/mcp", "oauth",
     "Ask about product analytics, feature flags and errors in PostHog."),
    ("amplitude", "Amplitude", "Amplitude", "data", "https://mcp.amplitude.com/mcp", "oauth",
     "Look at charts, dashboards and experiments in Amplitude."),
    ("mixpanel", "Mixpanel", "Mixpanel", "data", "https://mcp.mixpanel.com/mcp", "oauth",
     "Query events, funnels and reports in Mixpanel."),
    ("pendo", "Pendo", "Pendo", "data", "https://app.pendo.io/mcp/v0/shttp", "oauth",
     "Look at product usage and feedback in Pendo."),
    ("hex", "Hex", "Hex", "data", "https://app.hex.tech/mcp", "oauth",
     "Run and read Hex projects and data notebooks."),
    ("grafana", "Grafana", "Grafana Labs", "data", "https://mcp.grafana.com/mcp", "oauth",
     "Query dashboards, metrics and logs in Grafana Cloud."),
    ("datadog", "Datadog", "Datadog", "data", "https://mcp.datadoghq.com/api/unstable/mcp-server/mcp", "oauth",
     "Search logs, metrics, monitors and incidents in Datadog."),
    ("honeycomb", "Honeycomb", "Honeycomb", "data", "https://mcp.honeycomb.io/mcp", "oauth",
     "Query traces and events in Honeycomb."),
    ("stripe", "Stripe", "Stripe", "finance", "https://mcp.stripe.com", "oauth",
     "Look up payments, customers and invoices in Stripe."),
    ("paypal", "PayPal", "PayPal", "finance", "https://mcp.paypal.com/mcp", "oauth",
     "Work with PayPal invoices, orders and transactions."),
    ("square", "Square", "Block", "finance", "https://mcp.squareup.com/mcp", "oauth",
     "Look at Square payments, orders, items and customers."),
    ("ramp", "Ramp", "Ramp", "finance", "https://mcp.ramp.com/mcp", "oauth",
     "Look at spending, cards and bills in Ramp."),
    ("mercury", "Mercury", "Mercury", "finance", "https://mcp.mercury.com/mcp", "oauth",
     "Read accounts and transactions in Mercury banking."),
    ("close", "Close", "Close", "sales", "https://mcp.close.com/mcp", "oauth",
     "Find leads, contacts and deals in the Close CRM."),
    ("attio", "Attio", "Attio", "sales", "https://mcp.attio.com/mcp", "oauth",
     "Search and update records, lists and notes in the Attio CRM."),
    ("apollo", "Apollo.io", "Apollo", "sales", "https://mcp.apollo.io/mcp", "oauth",
     "Find people and companies and manage sequences in Apollo."),
    ("clay", "Clay", "Clay", "sales", "https://api.clay.com/v3/mcp", "oauth",
     "Research companies and people with Clay."),
    ("klaviyo", "Klaviyo", "Klaviyo", "sales", "https://mcp.klaviyo.com/mcp", "oauth",
     "Look at email campaigns, flows and audiences in Klaviyo."),
    ("webflow", "Webflow", "Webflow", "sales", "https://mcp.webflow.com/mcp", "oauth",
     "Edit Webflow sites, pages and CMS items."),
    ("wix", "Wix", "Wix", "sales", "https://mcp.wix.com/mcp", "oauth",
     "Manage your Wix site, store and bookings."),
    ("guru", "Guru", "Guru", "productivity", "https://mcp.api.getguru.com/mcp", "oauth",
     "Search your team's knowledge cards in Guru."),
    ("ahrefs", "Ahrefs", "Ahrefs", "research", "https://api.ahrefs.com/mcp/mcp", "oauth",
     "SEO data: backlinks, keywords and site traffic."),
    ("semrush", "Semrush", "Semrush", "research", "https://mcp.semrush.com/v1/mcp", "oauth",
     "Keyword, traffic and competitor data from Semrush."),
    ("tavily", "Tavily", "Tavily", "research", "https://mcp.tavily.com/mcp", "oauth",
     "Web search and page extraction made for AI assistants."),
    ("exa", "Exa", "Exa", "research", "https://mcp.exa.ai/mcp", "open",
     "Search the web, code and companies with Exa."),
    ("firecrawl", "Firecrawl", "Firecrawl", "research", "https://mcp.firecrawl.dev/mcp", "open",
     "Read and crawl websites into clean text."),
    ("apify", "Apify", "Apify", "research", "https://mcp.apify.com", "oauth",
     "Run thousands of ready-made scrapers and tools from Apify Store."),
    ("biorender", "BioRender", "BioRender", "research", "https://mcp.services.biorender.com/mcp", "oauth",
     "Find scientific icons and templates in BioRender."),
    ("kiwi", "Kiwi.com", "Kiwi.com", "travel", "https://mcp.kiwi.com", "open",
     "Search flights and compare prices."),
    ("zapier", "Zapier", "Zapier", "automation", "https://mcp.zapier.com/api/mcp/mcp", "oauth",
     "Use thousands of apps through your Zapier actions."),
    ("make", "Make", "Make", "automation", "https://mcp.make.com", "oauth",
     "Run your Make scenarios as tools."),
    ("pipedream", "Pipedream", "Pipedream", "automation", "https://remote.mcp.pipedream.net", "oauth",
     "Use thousands of app APIs through Pipedream."),
    ("mail", "Mail (Gmail, Outlook, ukr.net…)", "Lanterna", "communication", "", "builtin:mail",
     "Read, search and sort your mail into folders or labels; drafts and sending only after you confirm."),
    ("gdrive-builtin", "Google Drive", "Lanterna", "files", "", "builtin:gdrive",
     "Create folders and save files in your Google Drive, after you confirm."),
]

# In Claude's list, but these services only let apps they approved sign in (checked 8 November 2026).
_CLOSED = [
    ("gmail", "Gmail", "Google", "communication", "mail",
     "Google lets only apps it has checked use its Gmail connector. Use Mail instead: it works with Gmail through an app password."),
    ("gcal", "Google Calendar", "Google", "communication", "",
     "Google lets only apps it has checked use its Calendar connector. Reminders and regular tasks in Lanterna can stand in for now."),
    ("m365", "Microsoft 365 (Outlook, OneDrive)", "Microsoft", "communication", "",
     "Microsoft lets only apps registered with it read Outlook mail and OneDrive. Lanterna isn't one yet."),
    ("slack", "Slack", "Slack", "communication", "",
     "Slack lets only apps it approved use its connector."),
    ("figma", "Figma", "Figma", "design", "",
     "Figma lets only a few apps it approved use its connector."),
    ("hubspot", "HubSpot", "HubSpot", "sales", "",
     "HubSpot lets only apps registered with it use its connector."),
    ("box", "Box", "Box", "files", "",
     "Box lets only apps registered with it use its connector."),
    ("docusign", "Docusign", "Docusign", "files", "",
     "Docusign lets only apps registered with it use its connector."),
    ("pagerduty", "PagerDuty", "PagerDuty", "development", "",
     "PagerDuty lets only apps registered with it use its connector."),
    ("smartsheet", "Smartsheet", "Smartsheet", "productivity", "",
     "Smartsheet lets only apps registered with it use its connector."),
    ("wordpress", "WordPress.com", "Automattic", "sales", "",
     "WordPress.com didn't accept Lanterna's sign-in."),
    ("similarweb", "Similarweb", "Similarweb", "research", "",
     "Similarweb lets only apps it approved use its connector."),
]

CATEGORIES = {"productivity": "Productivity", "communication": "Mail and meetings", "files": "Files",
              "design": "Design", "development": "Development", "data": "Data and analytics", "finance": "Finance",
              "sales": "Sales and websites", "research": "Search and research", "automation": "Automation",
              "travel": "Travel"}

CATALOG: list[dict] = [
    {"id": i, "name": n, "by": b, "cat": c, "url": u, "auth": a.split(":")[0] if a.startswith("builtin") else a,
     "builtin": a.split(":", 1)[1] if a.startswith("builtin") else "", "about": d, "official": True}
    for i, n, b, c, u, a, d in _READY
] + [
    {"id": i, "name": n, "by": b, "cat": c, "url": "", "auth": "closed", "builtin": "", "about": "", "why": w,
     "instead": alt, "official": True}
    for i, n, b, c, alt, w in _CLOSED
]
BY_ID = {c["id"]: c for c in CATALOG}


def find(q: str) -> list[dict]:
    """Ready-made connectors matching the words (name, maker, what it does), best first."""
    words = [w for w in re.split(r"\W+", (q or "").lower()) if w]
    if not words:
        return list(CATALOG)
    out = []
    for c in CATALOG:
        name, hay = c["name"].lower(), " ".join([c["name"], c["by"], c["about"], c.get("why", ""), c["cat"]]).lower()
        if all(w in hay for w in words):
            out.append((0 if any(name.startswith(w) or f" {w}" in f" {name}" for w in words) else 1, c))
    return [c for _, c in sorted(out, key=lambda x: x[0])]


# ---------------------------------------------------------------- the public MCP Registry
def _domain(namespace: str) -> str:
    """"com.notion" → "notion.com"; "io.github.someone" → "" (a GitHub account, not a checked domain)."""
    parts = namespace.split(".")
    if namespace.startswith("io.github.") or len(parts) < 2:
        return ""
    return ".".join(reversed(parts))


def _host(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def _entry(item: dict) -> dict | None:
    s = item.get("server") if isinstance(item, dict) else None
    if not isinstance(s, dict) or not s.get("name"):
        return None
    name = str(s["name"])
    ns = name.split("/")[0]
    dom = _domain(ns)
    by = dom or ("GitHub: " + ns[len("io.github."):] if ns.startswith("io.github.") else ns)
    title = str(s.get("title") or name.split("/")[-1].replace("-", " ").strip() or name)[:60]
    out = {"id": "reg:" + name, "name": title, "by": by, "about": " ".join(str(s.get("description") or "").split())[:200],
           "cat": "", "registry": name, "version": str(s.get("version") or "")}
    for r in s.get("remotes") or []:
        url = str(r.get("url") or "") if isinstance(r, dict) else ""
        if r.get("type") == "streamable-http" and url.startswith("https://") and "{" not in url:
            heads = [{"name": str(h.get("name")), "secret": bool(h.get("isSecret")), "about": str(h.get("description") or "")[:120]}
                     for h in r.get("headers") or [] if isinstance(h, dict) and h.get("name") and h.get("isRequired")]
            host = _host(url)
            official = bool(dom) and (host == dom or host.endswith("." + dom))
            return {**out, "kind": "http", "url": url, "headers": heads, "official": official,
                    "through": "" if official else host}
    for p in s.get("packages") or []:
        if not isinstance(p, dict) or (p.get("transport") or {}).get("type", "stdio") != "stdio":
            continue
        pkg, ver = str(p.get("identifier") or ""), str(p.get("version") or "")
        if not pkg or not re.fullmatch(r"[@\w./-]+", pkg) or not re.fullmatch(r"[\w.+-]*", ver):
            continue
        if p.get("registryType") == "npm":
            cmd = ["npx", "-y", f"{pkg}@{ver}" if ver else pkg]
            needs = "node"
        elif p.get("registryType") == "pypi":
            cmd = ["uvx", f"{pkg}=={ver}" if ver else pkg]
            needs = "uv"
        else:
            continue
        env = [{"name": str(e.get("name")), "secret": bool(e.get("isSecret")), "about": str(e.get("description") or "")[:120]}
               for e in p.get("environmentVariables") or [] if isinstance(e, dict) and e.get("name") and e.get("isRequired")]
        return {**out, "kind": "stdio", "command": cmd, "needs": needs, "env": env, "official": False, "through": ""}
    return None


def search_registry(q: str, cursor: str = "", client: httpx.Client | None = None, limit: int = 40) -> dict:
    """{"items": [...], "next": cursor or ""}: servers from the public registry that Lanterna can run."""
    params = {"version": "latest", "limit": str(limit)}
    if q.strip():
        params["search"] = q.strip()[:80]
    if cursor:
        params["cursor"] = cursor[:300]
    own = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=True)
    try:
        r = client.get(REGISTRY, params=params, headers={"Accept": "application/json", "User-Agent": f"Lanterna/{__version__}"})
        d = r.json() if r.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        d = {}
    finally:
        if own:
            client.close()
    items, seen = [], set()
    for it in d.get("servers") or [] if isinstance(d, dict) else []:
        e = _entry(it)
        if e and e["id"] not in seen:
            seen.add(e["id"])
            items.append(e)
    nxt = str(((d.get("metadata") or {}).get("nextCursor") or "")) if isinstance(d, dict) else ""
    return {"items": items, "next": nxt, "ok": bool(d)}
