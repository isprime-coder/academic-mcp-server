"""
Academic MCP Server for Claude Code CLI
Features: Semantic Scholar search, arXiv search, DOI verification, GitHub README, GitHub CLI integration, BibTeX output
"""

import json
import re
import shutil
import sqlite3
import subprocess
import time
import asyncio
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, quote

import arxiv
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Create MCP Server instance
server = Server("academic-mcp-server")

# API Base URLs
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"
CROSSREF_API = "https://api.crossref.org/works"
GITHUB_API = "https://api.github.com/repos"

# Cache config - cache directory is in project root
CACHE_DIR = Path(__file__).parent.parent.parent / "Cache"
CACHE_DB = CACHE_DIR / "cache.db"
CACHE_EXPIRY_SECONDS = 86400  # 24 hours

# Retry config
MAX_RETRIES = 3
RETRY_DELAY = 1.0
RETRY_BACKOFF = 2.0


def init_cache():
    """Initialize cache database"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            data TEXT,
            timestamp REAL
        )
    """)
    conn.commit()
    conn.close()


def get_cache(key: str) -> dict | None:
    """Get data from cache"""
    try:
        conn = sqlite3.connect(str(CACHE_DB))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data, timestamp FROM cache WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            data, timestamp = row
            if time.time() - timestamp < CACHE_EXPIRY_SECONDS:
                return json.loads(data)
    except Exception:
        pass
    return None


def set_cache(key: str, data: dict):
    """Set cache data"""
    try:
        conn = sqlite3.connect(str(CACHE_DB))
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO cache (key, data, timestamp) VALUES (?, ?, ?)",
            (key, json.dumps(data), time.time())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def with_retry(max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY, backoff: float = RETRY_BACKOFF):
    """Retry decorator"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (backoff ** attempt)
                        await asyncio.sleep(wait_time)
            raise last_exception
        return wrapper
    return decorator


# Initialize cache
init_cache()


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools"""
    return [
        Tool(
            name="search_papers",
            description="""Search academic papers (Semantic Scholar + arXiv)

Usage:
- Search published papers and preprints
- Supports keyword, author, title search
- Returns title, authors, year, abstract, citation count, DOI, etc.

Parameters:
- query: Search keyword (required)
- limit: Number of results, default 5
- year_range: Year range, e.g., "2020-2024"
- source: Data source - "all", "semantic", "arxiv"
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword"},
                    "limit": {"type": "integer", "default": 5, "description": "Number of results"},
                    "year_range": {"type": "string", "description": "Year range, e.g., 2020-2024"},
                    "source": {"type": "string", "default": "all", "enum": ["all", "semantic", "arxiv"]},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_paper_details",
            description="""Get paper details

Usage:
- Get full info by paper ID
- Includes abstract, references, citations, author details

Parameters:
- paper_id: Paper ID (Semantic Scholar ID or arXiv ID)
- source: Data source - "semantic" or "arxiv"
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "Paper ID"},
                    "source": {"type": "string", "default": "semantic", "enum": ["semantic", "arxiv"]},
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="verify_doi",
            description="""Verify DOI authenticity and get metadata

Usage:
- Verify if a DOI exists
- Get paper title, authors, journal, year, etc.
- Verify citation accuracy for academic writing

Parameters:
- doi: DOI identifier (e.g., 10.1038/nature14539)
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "doi": {"type": "string", "description": "DOI identifier"},
                },
                "required": ["doi"],
            },
        ),
        Tool(
            name="get_bibtex",
            description="""Get BibTeX citation format

Usage:
- Generate BibTeX entry for LaTeX
- Support DOI or paper ID
- Quick citation for paper writing

Parameters:
- doi: DOI identifier (priority)
- paper_id: Semantic Scholar paper ID (alternative)
- paper_title: Paper title (for search, alternative)
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "doi": {"type": "string", "description": "DOI identifier"},
                    "paper_id": {"type": "string", "description": "Semantic Scholar paper ID"},
                    "paper_title": {"type": "string", "description": "Paper title (for search)"},
                },
            },
        ),
        Tool(
            name="fetch_github_readme",
            description="""Get GitHub repository README

Usage:
- Read official library documentation
- Get installation and usage instructions
- Understand library features and API

Parameters:
- repo_url: GitHub URL or owner/repo format
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_url": {"type": "string", "description": "GitHub URL or owner/repo"},
                },
                "required": ["repo_url"],
            },
        ),
        Tool(
            name="search_github",
            description="""Search GitHub using CLI

Usage:
- Search repositories
- Search code snippets
- Find open source projects

Parameters:
- query: Search keyword
- type: Search type - "repos" or "code"
- limit: Number of results, default 10
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword"},
                    "type": {"type": "string", "default": "repos", "enum": ["repos", "code"]},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_github_repo_info",
            description="""Get GitHub repository details

Usage:
- View stars, forks, description
- Get README content
- View latest release info

Parameters:
- repo: Repository name, format owner/repo
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository name, e.g., huggingface/transformers"},
                },
                "required": ["repo"],
            },
        ),
        Tool(
            name="get_citations",
            description="""Get paper citation relationships

Usage:
- View what papers a paper cites
- View what papers cite a paper
- For literature review and research tracking

Parameters:
- paper_id: Paper ID (Semantic Scholar ID)
- direction: "forward" (cited by) or "backward" (cites)
- limit: Number of results, default 10
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "Semantic Scholar paper ID"},
                    "direction": {"type": "string", "default": "forward", "enum": ["forward", "backward"]},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="get_pdf_links",
            description="""Get paper PDF download links

Usage:
- Get arXiv paper PDF links
- Get open access PDF links
- Easy download for reading

Parameters:
- paper_id: Paper ID (arXiv ID or Semantic Scholar ID)
- source: Data source - "arxiv" or "semantic"
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "Paper ID"},
                    "source": {"type": "string", "default": "arxiv", "enum": ["arxiv", "semantic"]},
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="get_similar_papers",
            description="""Get similar paper recommendations

Usage:
- Discover related research areas
- Expand literature review
- Find similar methods

Parameters:
- paper_id: Paper ID (Semantic Scholar ID)
- limit: Number of results, default 5
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "Semantic Scholar paper ID"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="search_author",
            description="""Search author information

Usage:
- Find all papers by an author
- Track author research direction
- Get author citation statistics

Parameters:
- author_name: Author name
- limit: Number of results, default 10
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "author_name": {"type": "string", "description": "Author name"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["author_name"],
            },
        ),
        Tool(
            name="get_citation_formats",
            description="""Get multiple citation formats

Usage:
- Generate different citation formats
- Support APA, MLA, Chicago, IEEE, Vancouver
- Easy copy to different documents

Parameters:
- doi: DOI identifier
- paper_id: Semantic Scholar paper ID (alternative)
- format: Citation format, default returns all
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "doi": {"type": "string", "description": "DOI identifier"},
                    "paper_id": {"type": "string", "description": "Semantic Scholar paper ID"},
                    "format": {"type": "string", "default": "all", "enum": ["all", "apa", "mla", "chicago", "ieee", "vancouver"]},
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls"""
    try:
        if name == "search_papers":
            return await search_papers(**arguments)
        elif name == "get_paper_details":
            return await get_paper_details(**arguments)
        elif name == "verify_doi":
            return await verify_doi(**arguments)
        elif name == "get_bibtex":
            return await get_bibtex(**arguments)
        elif name == "fetch_github_readme":
            return await fetch_github_readme(**arguments)
        elif name == "search_github":
            return await search_github(**arguments)
        elif name == "get_github_repo_info":
            return await get_github_repo_info(**arguments)
        elif name == "get_citations":
            return await get_citations(**arguments)
        elif name == "get_pdf_links":
            return await get_pdf_links(**arguments)
        elif name == "get_similar_papers":
            return await get_similar_papers(**arguments)
        elif name == "search_author":
            return await search_author(**arguments)
        elif name == "get_citation_formats":
            return await get_citation_formats(**arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def search_papers(
    query: str,
    limit: int = 5,
    year_range: str | None = None,
    source: str = "all",
) -> list[TextContent]:
    """Search academic papers"""
    results = []

    # Check cache
    cache_key = f"search:{query}:{limit}:{year_range}:{source}"
    cached = get_cache(cache_key)
    if cached:
        return [TextContent(type="text", text=cached["output"])]

    # Build year filter
    year_filter = ""
    if year_range:
        year_filter = f"&year={year_range}"

    # Semantic Scholar search
    if source in ["all", "semantic"]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            encoded_query = quote(query)
            url = f"{SEMANTIC_SCHOLAR_API}/paper/search?query={encoded_query}&limit={limit}{year_filter}&fields=title,authors,year,abstract,citationCount,doi,url,venue,openAccessPdf"
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                for paper in data.get("data", []):
                    authors = ", ".join([a.get("name", "") for a in paper.get("authors", [])])
                    oa_pdf = paper.get("openAccessPdf")
                    results.append({
                        "source": "Semantic Scholar",
                        "id": paper.get("paperId"),
                        "title": paper.get("title"),
                        "authors": authors,
                        "year": paper.get("year"),
                        "abstract": paper.get("abstract", "")[:500] + "..." if paper.get("abstract") and len(paper.get("abstract", "")) > 500 else paper.get("abstract"),
                        "citations": paper.get("citationCount"),
                        "doi": paper.get("doi"),
                        "url": paper.get("url"),
                        "venue": paper.get("venue"),
                        "pdf": oa_pdf.get("url") if oa_pdf else None,
                    })

    # arXiv search
    if source in ["all", "arxiv"]:
        search = arxiv.Search(
            query=query,
            max_results=limit,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        client = arxiv.Client()
        for paper in client.results(search):
            authors = ", ".join([a.name for a in paper.authors[:3]])
            if len(paper.authors) > 3:
                authors += " et al."
            results.append({
                "source": "arXiv",
                "id": paper.entry_id.split("/")[-1],
                "title": paper.title,
                "authors": authors,
                "year": paper.published.year if paper.published else None,
                "abstract": paper.summary[:500] + "..." if len(paper.summary) > 500 else paper.summary,
                "citations": None,
                "doi": paper.doi,
                "url": paper.entry_id,
                "venue": "arXiv",
                "pdf": paper.pdf_url,
            })

    if not results:
        return [TextContent(type="text", text="No papers found")]

    # Format output
    output = f"# Search Results: \"{query}\"\n\n"
    for i, r in enumerate(results, 1):
        output += f"## [{i}] {r['title']}\n"
        output += f"- **Source**: {r['source']}"
        if r['venue']:
            output += f" | {r['venue']}"
        output += "\n"
        output += f"- **Authors**: {r['authors']}\n"
        if r['year']:
            output += f"- **Year**: {r['year']}\n"
        if r['citations'] is not None:
            output += f"- **Citations**: {r['citations']}\n"
        if r['doi']:
            output += f"- **DOI**: {r['doi']}\n"
        output += f"- **ID**: {r['id']}\n"
        output += f"- **URL**: {r['url']}\n"
        if r.get('pdf'):
            output += f"- **PDF**: {r['pdf']}\n"
        if r['abstract']:
            output += f"- **Abstract**: {r['abstract']}\n"
        output += "\n"

    # Save to cache
    set_cache(cache_key, {"output": output})

    return [TextContent(type="text", text=output)]


async def get_paper_details(paper_id: str, source: str = "semantic") -> list[TextContent]:
    """Get paper details"""
    if source == "semantic":
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{SEMANTIC_SCHOLAR_API}/paper/{paper_id}?fields=title,authors,year,abstract,citationCount,referenceCount,doi,url,venue,references.title,references.authors,references.year,citations.title,citations.authors,citations.year"
            response = await client.get(url)
            if response.status_code != 200:
                return [TextContent(type="text", text=f"Failed to get paper: HTTP {response.status_code}")]
            data = response.json()

        output = f"# {data.get('title', 'Unknown')}\n\n"
        authors = ", ".join([a.get("name", "") for a in data.get("authors", [])])
        output += f"- **Authors**: {authors}\n"
        output += f"- **Year**: {data.get('year')}\n"
        output += f"- **Venue**: {data.get('venue', 'N/A')}\n"
        output += f"- **Citations**: {data.get('citationCount')}\n"
        output += f"- **References**: {data.get('referenceCount')}\n"
        output += f"- **DOI**: {data.get('doi', 'N/A')}\n"
        output += f"- **URL**: {data.get('url')}\n\n"
        output += f"## Abstract\n{data.get('abstract', 'N/A')}\n\n"

        # References
        refs = data.get("references", [])[:5]
        if refs:
            output += "## References\n"
            for i, ref in enumerate(refs, 1):
                ref_authors = ", ".join([a.get("name", "") for a in ref.get("authors", [])[:2]])
                output += f"{i}. {ref.get('title', 'N/A')} ({ref_authors}, {ref.get('year', 'N/A')})\n"

        return [TextContent(type="text", text=output)]

    elif source == "arxiv":
        search = arxiv.Search(id_list=[paper_id])
        paper = next(search.results(), None)
        if not paper:
            return [TextContent(type="text", text="arXiv paper not found")]

        output = f"# {paper.title}\n\n"
        authors = ", ".join([a.name for a in paper.authors])
        output += f"- **Authors**: {authors}\n"
        output += f"- **Published**: {paper.published}\n"
        output += f"- **Updated**: {paper.updated}\n"
        output += f"- **DOI**: {paper.doi or 'N/A'}\n"
        output += f"- **URL**: {paper.entry_id}\n"
        output += f"- **PDF**: {paper.pdf_url}\n\n"
        output += f"## Abstract\n{paper.summary}\n"

        return [TextContent(type="text", text=output)]

    return [TextContent(type="text", text="Unsupported source")]


async def verify_doi(doi: str) -> list[TextContent]:
    """Verify DOI and get metadata"""
    # Clean DOI
    doi = doi.strip()
    if doi.startswith("doi:"):
        doi = doi[4:]
    if doi.startswith("https://doi.org/"):
        doi = doi[16:]

    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{CROSSREF_API}/{doi}"
        response = await client.get(url)

        if response.status_code == 200:
            data = response.json()
            work = data.get("message", {})

            title = work.get("title", ["N/A"])[0]
            authors = ", ".join([
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in work.get("author", [])
            ])
            year = work.get("published-print", {}).get("date-parts", [[None]])[0][0]
            year = year or work.get("published-online", {}).get("date-parts", [[None]])[0][0]
            venue = work.get("container-title", ["N/A"])[0]
            publisher = work.get("publisher", "N/A")
            type_ = work.get("type", "N/A")

            output = f"# DOI Verification Result\n\n"
            output += f"**Status**: ✅ Valid\n\n"
            output += f"## Metadata\n"
            output += f"- **Title**: {title}\n"
            output += f"- **Authors**: {authors}\n"
            output += f"- **Year**: {year}\n"
            output += f"- **Venue**: {venue}\n"
            output += f"- **Publisher**: {publisher}\n"
            output += f"- **Type**: {type_}\n"
            output += f"- **DOI**: {doi}\n\n"
            output += f"## Citation\n"
            output += f"```\n{authors} ({year}). {title}. {venue}.\nDOI: {doi}\n```"

            return [TextContent(type="text", text=output)]
        else:
            return [TextContent(type="text", text=f"DOI Verification Failed: HTTP {response.status_code}\nDOI \"{doi}\" does not exist or is invalid")]


async def fetch_github_readme(repo_url: str) -> list[TextContent]:
    """Get GitHub README"""
    # Parse repo info
    if "github.com" in repo_url:
        parts = urlparse(repo_url).path.strip("/").split("/")
        owner, repo = parts[0], parts[1]
    else:
        owner, repo = repo_url.split("/")[-2:]

    # Remove .git suffix
    repo = repo.replace(".git", "")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try to get README.md
        readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md"
        response = await client.get(readme_url)

        if response.status_code != 200:
            # Try master branch
            readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/README.md"
            response = await client.get(readme_url)

        if response.status_code == 200:
            content = response.text
            output = f"# GitHub README: {owner}/{repo}\n\n"
            output += f"**URL**: https://github.com/{owner}/{repo}\n\n"
            output += "---\n\n"
            output += content
            return [TextContent(type="text", text=output)]
        else:
            return [TextContent(type="text", text=f"Failed to get README: HTTP {response.status_code}\nPlease check the repository address")]


async def get_citations(paper_id: str, direction: str = "forward", limit: int = 10) -> list[TextContent]:
    """Get citation relationships"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        if direction == "forward":
            url = f"{SEMANTIC_SCHOLAR_API}/paper/{paper_id}/citations?limit={limit}&fields=title,authors,year,venue"
            field_name = "Cited By"
        else:
            url = f"{SEMANTIC_SCHOLAR_API}/paper/{paper_id}/references?limit={limit}&fields=title,authors,year,venue"
            field_name = "References"

        response = await client.get(url)
        if response.status_code != 200:
            return [TextContent(type="text", text=f"Failed to get citations: HTTP {response.status_code}")]

        data = response.json()
        citations = data.get("data", [])

        if not citations:
            return [TextContent(type="text", text=f"No {field_name} found")]

        output = f"# {field_name}\n\n"
        output += f"**Paper ID**: {paper_id}\n"
        output += f"**Direction**: {field_name}\n"
        output += f"**Count**: {len(citations)}\n\n"

        for i, item in enumerate(citations, 1):
            if direction == "forward":
                paper = item.get("citingPaper", {})
            else:
                paper = item.get("citedPaper", {})

            title = paper.get("title", "N/A")
            authors = ", ".join([a.get("name", "") for a in paper.get("authors", [])[:3]])
            year = paper.get("year", "N/A")
            venue = paper.get("venue", "")

            output += f"## [{i}] {title}\n"
            output += f"- **Authors**: {authors}\n"
            output += f"- **Year**: {year}\n"
            if venue:
                output += f"- **Venue**: {venue}\n"
            output += "\n"

        return [TextContent(type="text", text=output)]


def generate_bibtex(
    title: str,
    authors: list[str],
    year: int | str | None,
    venue: str | None = None,
    doi: str | None = None,
    paper_type: str = "article",
) -> str:
    """Generate BibTeX citation"""
    # Generate cite key
    first_author = authors[0].split()[-1].lower() if authors else "unknown"
    year_str = str(year) if year else "nodate"
    title_word = re.sub(r'[^a-zA-Z]', '', title.split()[0].lower()) if title else "title"
    cite_key = f"{first_author}{year_str}{title_word}"

    # Build BibTeX entry
    bibtex = f"@{paper_type}{{{cite_key},\n"
    bibtex += f"  title={{{title}}},\n"

    if authors:
        bibtex += f"  author={{{' and '.join(authors)}}},\n"

    if year:
        bibtex += f"  year={{{year}}},\n"

    if venue:
        if paper_type == "article":
            bibtex += f"  journal={{{venue}}},\n"
        else:
            bibtex += f"  booktitle={{{venue}}},\n"

    if doi:
        bibtex += f"  doi={{{doi}}},\n"

    bibtex += "}"

    return bibtex


async def get_bibtex(
    doi: str | None = None,
    paper_id: str | None = None,
    paper_title: str | None = None,
) -> list[TextContent]:
    """Get BibTeX citation"""
    # Prefer DOI
    if doi:
        doi = doi.strip()
        if doi.startswith("doi:"):
            doi = doi[4:]
        if doi.startswith("https://doi.org/"):
            doi = doi[16:]

        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{CROSSREF_API}/{doi}"
            response = await client.get(url)

            if response.status_code == 200:
                data = response.json()
                work = data.get("message", {})

                title = work.get("title", ["N/A"])[0]
                authors = [
                    f"{a.get('given', '')} {a.get('family', '')}".strip()
                    for a in work.get("author", [])
                ]
                year = work.get("published-print", {}).get("date-parts", [[None]])[0][0]
                year = year or work.get("published-online", {}).get("date-parts", [[None]])[0][0]
                venue = work.get("container-title", [""])[0] or None
                type_ = work.get("type", "article")

                # Map types
                type_map = {
                    "journal-article": "article",
                    "conference-paper": "inproceedings",
                    "book": "book",
                    "book-chapter": "incollection",
                }
                bibtex_type = type_map.get(type_, "article")

                bibtex = generate_bibtex(title, authors, year, venue, doi, bibtex_type)

                output = f"# BibTeX Citation\n\n"
                output += f"**Paper**: {title}\n\n"
                output += "```bibtex\n"
                output += bibtex
                output += "\n```\n"
                return [TextContent(type="text", text=output)]
            else:
                return [TextContent(type="text", text=f"Failed to get DOI info: HTTP {response.status_code}")]

    # Use Semantic Scholar ID
    if paper_id:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{SEMANTIC_SCHOLAR_API}/paper/{paper_id}?fields=title,authors,year,venue,doi"
            response = await client.get(url)

            if response.status_code == 200:
                data = response.json()
                title = data.get("title", "N/A")
                authors = [a.get("name", "") for a in data.get("authors", [])]
                year = data.get("year")
                venue = data.get("venue") or None
                doi_found = data.get("doi")

                bibtex = generate_bibtex(title, authors, year, venue, doi_found)

                output = f"# BibTeX Citation\n\n"
                output += f"**Paper**: {title}\n\n"
                output += "```bibtex\n"
                output += bibtex
                output += "\n```\n"
                return [TextContent(type="text", text=output)]
            else:
                return [TextContent(type="text", text=f"Failed to get paper info: HTTP {response.status_code}")]

    # Use title search
    if paper_title:
        async with httpx.AsyncClient(timeout=30.0) as client:
            encoded_query = quote(paper_title)
            url = f"{SEMANTIC_SCHOLAR_API}/paper/search?query={encoded_query}&limit=1&fields=title,authors,year,venue,doi"
            response = await client.get(url)

            if response.status_code == 200:
                data = response.json()
                papers = data.get("data", [])
                if papers:
                    paper = papers[0]
                    title = paper.get("title", "N/A")
                    authors = [a.get("name", "") for a in paper.get("authors", [])]
                    year = paper.get("year")
                    venue = paper.get("venue") or None
                    doi_found = paper.get("doi")

                    bibtex = generate_bibtex(title, authors, year, venue, doi_found)

                    output = f"# BibTeX Citation\n\n"
                    output += f"**Paper**: {title}\n\n"
                    output += "```bibtex\n"
                    output += bibtex
                    output += "\n```\n"
                    return [TextContent(type="text", text=output)]
                else:
                    return [TextContent(type="text", text=f"No paper found with title \"{paper_title}\"")]

    return [TextContent(type="text", text="Please provide doi, paper_id or paper_title")]


def run_gh_command(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    """Execute GitHub CLI command"""
    gh_path = shutil.which("gh")
    if not gh_path:
        # Try common paths
        common_paths = [
            r"C:\Program Files\GitHub CLI\gh.exe",
            r"C:\Program Files (x86)\GitHub CLI\gh.exe",
            "/usr/local/bin/gh",
            "/usr/bin/gh",
        ]
        for path in common_paths:
            if shutil.which(path):
                gh_path = path
                break

    if not gh_path:
        return False, "GitHub CLI not installed. Visit https://cli.github.com/ to install"

    try:
        result = subprocess.run(
            [gh_path] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='utf-8',
            errors='replace'
        )

        if result.returncode == 0:
            return True, result.stdout
        else:
            error_msg = result.stderr.strip() or result.stdout.strip()
            if "not logged in" in error_msg.lower() or "authentication" in error_msg.lower():
                return False, f"GitHub CLI not logged in. Run: gh auth login\n{error_msg}"
            return False, f"Command failed: {error_msg}"

    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, f"Error: {str(e)}"


async def search_github(
    query: str,
    type: str = "repos",
    limit: int = 10,
) -> list[TextContent]:
    """Search GitHub using CLI"""
    # Build search command
    if type == "repos":
        args = ["search", "repos", query, "--limit", str(limit), "--json", "name,owner,description,stargazersCount,forksCount,updatedAt,url"]
    else:
        args = ["search", "code", query, "--limit", str(limit), "--json", "path,repository"]

    success, result = run_gh_command(args)

    if not success:
        return [TextContent(type="text", text=result)]

    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return [TextContent(type="text", text=f"Failed to parse result: {result[:500]}")]

    if not data:
        return [TextContent(type="text", text="No matching results found")]

    output = f"# GitHub Search Results: \"{query}\"\n\n"
    output += f"**Type**: {type}\n"
    output += f"**Count**: {len(data)}\n\n"

    if type == "repos":
        for i, repo in enumerate(data, 1):
            name = repo.get("name", "N/A")
            owner = repo.get("owner", {}).get("login", "unknown")
            desc = repo.get("description", "") or "No description"
            stars = repo.get("stargazersCount", 0)
            forks = repo.get("forksCount", 0)
            url = repo.get("url", f"https://github.com/{owner}/{name}")

            output += f"## [{i}] {owner}/{name}\n"
            output += f"- **Description**: {desc}\n"
            output += f"- **Stars**: {stars:,} | **Forks**: {forks:,}\n"
            output += f"- **URL**: {url}\n\n"
    else:
        for i, item in enumerate(data, 1):
            path = item.get("path", "N/A")
            repo = item.get("repository", {})
            repo_name = f"{repo.get('owner', {}).get('login', 'unknown')}/{repo.get('name', 'N/A')}"

            output += f"## [{i}] {repo_name}\n"
            output += f"- **File**: {path}\n"
            output += f"- **URL**: https://github.com/{repo_name}/blob/main/{path}\n\n"

    return [TextContent(type="text", text=output)]


async def get_github_repo_info(repo: str) -> list[TextContent]:
    """Get GitHub repository details"""
    # Parse repo name
    if "github.com" in repo:
        parts = urlparse(repo).path.strip("/").split("/")
        owner, repo_name = parts[0], parts[1]
    else:
        owner, repo_name = repo.split("/")[-2:]

    # Get repo info
    args = ["repo", "view", f"{owner}/{repo_name}", "--json", "name,description,stargazerCount,forksCount,createdAt,updatedAt,primaryLanguage,homepageUrl,url"]

    success, result = run_gh_command(args)

    if not success:
        # Try direct API access
        async with httpx.AsyncClient(timeout=30.0) as client:
            api_url = f"https://api.github.com/repos/{owner}/{repo_name}"
            response = await client.get(api_url)
            if response.status_code == 200:
                data = response.json()
                output = f"# {owner}/{repo_name}\n\n"
                output += f"- **Description**: {data.get('description', 'No description')}\n"
                output += f"- **Language**: {data.get('language', 'N/A')}\n"
                output += f"- **Stars**: {data.get('stargazers_count', 0):,}\n"
                output += f"- **Forks**: {data.get('forks_count', 0):,}\n"
                output += f"- **Created**: {data.get('created_at', 'N/A')}\n"
                output += f"- **Updated**: {data.get('updated_at', 'N/A')}\n"
                output += f"- **Homepage**: {data.get('homepage', 'N/A')}\n"
                output += f"- **GitHub**: {data.get('html_url')}\n"
                return [TextContent(type="text", text=output)]
            else:
                return [TextContent(type="text", text=result)]

    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return [TextContent(type="text", text=f"Failed to parse result: {result[:500]}")]

    output = f"# {owner}/{repo_name}\n\n"
    output += f"- **Description**: {data.get('description', 'No description')}\n"

    lang = data.get('primaryLanguage', {})
    if lang:
        output += f"- **Language**: {lang.get('name', 'N/A')}\n"

    output += f"- **Stars**: {data.get('stargazerCount', 0):,}\n"
    output += f"- **Forks**: {data.get('forksCount', 0):,}\n"
    output += f"- **Created**: {data.get('createdAt', 'N/A')}\n"
    output += f"- **Updated**: {data.get('updatedAt', 'N/A')}\n"

    homepage = data.get('homepageUrl')
    if homepage:
        output += f"- **Homepage**: {homepage}\n"

    output += f"- **GitHub**: {data.get('url', f'https://github.com/{owner}/{repo_name}')}\n"

    # Try to get README
    readme_args = ["repo", "view", f"{owner}/{repo_name}", "--readme"]
    success, readme = run_gh_command(readme_args, timeout=60)

    if success and readme.strip():
        output += "\n---\n\n## README\n\n"
        output += readme[:3000]  # Limit length
        if len(readme) > 3000:
            output += "\n\n...(truncated)"

    return [TextContent(type="text", text=output)]


async def get_pdf_links(paper_id: str, source: str = "arxiv") -> list[TextContent]:
    """Get paper PDF download links"""
    # Check cache
    cache_key = f"pdf_links:{source}:{paper_id}"
    cached = get_cache(cache_key)
    if cached:
        return [TextContent(type="text", text=cached["output"])]

    if source == "arxiv":
        # arXiv PDF link format
        arxiv_id = paper_id
        if "arxiv.org" in paper_id:
            arxiv_id = paper_id.split("/")[-1]
        if paper_id.startswith("arXiv:"):
            arxiv_id = paper_id[6:]

        # Try to get paper info
        try:
            search = arxiv.Search(id_list=[arxiv_id])
            paper = next(search.results(), None)

            if paper:
                output = f"# PDF Download Links\n\n"
                output += f"**Paper**: {paper.title}\n"
                output += f"**arXiv ID**: {arxiv_id}\n\n"
                output += f"## Download Links\n"
                output += f"- **PDF**: {paper.pdf_url}\n"
                output += f"- **Homepage**: {paper.entry_id}\n\n"
                output += f"## Download Commands\n"
                output += f"```bash\n"
                output += f"# Using wget\n"
                output += f"wget {paper.pdf_url} -O {arxiv_id}.pdf\n\n"
                output += f"# Using curl\n"
                output += f"curl -L {paper.pdf_url} -o {arxiv_id}.pdf\n"
                output += f"```\n"

                set_cache(cache_key, {"output": output})
                return [TextContent(type="text", text=output)]
            else:
                # Construct link directly
                output = f"# PDF Download Links\n\n"
                output += f"**arXiv ID**: {arxiv_id}\n\n"
                output += f"## Download Links\n"
                output += f"- **PDF**: https://arxiv.org/pdf/{arxiv_id}.pdf\n"
                output += f"- **Homepage**: https://arxiv.org/abs/{arxiv_id}\n\n"
                output += f"## Download Commands\n"
                output += f"```bash\n"
                output += f"curl -L https://arxiv.org/pdf/{arxiv_id}.pdf -o {arxiv_id}.pdf\n"
                output += f"```\n"

                set_cache(cache_key, {"output": output})
                return [TextContent(type="text", text=output)]
        except Exception as e:
            output = f"# PDF Download Links\n\n"
            output += f"**arXiv ID**: {arxiv_id}\n\n"
            output += f"## Download Links\n"
            output += f"- **PDF**: https://arxiv.org/pdf/{arxiv_id}.pdf\n"
            output += f"- **Homepage**: https://arxiv.org/abs/{arxiv_id}\n\n"
            output += f"Note: Could not get paper details ({str(e)})\n"

            return [TextContent(type="text", text=output)]

    elif source == "semantic":
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{SEMANTIC_SCHOLAR_API}/paper/{paper_id}?fields=title,openAccessPdf,url"
            response = await client.get(url)

            if response.status_code != 200:
                return [TextContent(type="text", text=f"Failed to get paper info: HTTP {response.status_code}")]

            data = response.json()
            title = data.get("title", "N/A")
            oa_pdf = data.get("openAccessPdf")

            output = f"# PDF Download Links\n\n"
            output += f"**Paper**: {title}\n"
            output += f"**Semantic Scholar ID**: {paper_id}\n\n"

            if oa_pdf:
                pdf_url = oa_pdf.get("url")
                output += f"## Open Access PDF\n"
                output += f"- **PDF URL**: {pdf_url}\n"
                output += f"- **Status**: {oa_pdf.get('status', 'unknown')}\n\n"
                output += f"## Download Commands\n"
                output += f"```bash\n"
                output += f"curl -L \"{pdf_url}\" -o paper.pdf\n"
                output += f"```\n"
            else:
                output += f"## No Open Access PDF\n"
                output += f"This paper may need to be obtained through your university library or academic database.\n"
                output += f"- **Semantic Scholar page**: {data.get('url', 'N/A')}\n"

            set_cache(cache_key, {"output": output})
            return [TextContent(type="text", text=output)]

    return [TextContent(type="text", text="Unsupported source, please use 'arxiv' or 'semantic'")]


async def get_similar_papers(paper_id: str, limit: int = 5) -> list[TextContent]:
    """Get similar paper recommendations"""
    # Check cache
    cache_key = f"similar:{paper_id}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return [TextContent(type="text", text=cached["output"])]

    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{SEMANTIC_SCHOLAR_API}/paper/{paper_id}?fields=title,authors,year,similarPapers.title,similarPapers.authors,similarPapers.year,similarPapers.citationCount,similarPapers.url"
        response = await client.get(url)

        if response.status_code != 200:
            return [TextContent(type="text", text=f"Failed to get similar papers: HTTP {response.status_code}")]

        data = response.json()
        title = data.get("title", "Unknown")
        similar = data.get("similarPapers", [])[:limit]

        if not similar:
            return [TextContent(type="text", text="No similar papers found")]

        output = f"# Similar Papers\n\n"
        output += f"**Original Paper**: {title}\n"
        output += f"**Found {len(similar)} similar papers**\n\n"

        for i, paper in enumerate(similar, 1):
            paper_title = paper.get("title", "N/A")
            authors = ", ".join([a.get("name", "") for a in paper.get("authors", [])[:3]])
            year = paper.get("year", "N/A")
            citations = paper.get("citationCount", 0)
            url = paper.get("url", "")

            output += f"## [{i}] {paper_title}\n"
            output += f"- **Authors**: {authors}\n"
            output += f"- **Year**: {year}\n"
            output += f"- **Citations**: {citations}\n"
            if url:
                output += f"- **URL**: {url}\n"
            output += "\n"

        set_cache(cache_key, {"output": output})
        return [TextContent(type="text", text=output)]


async def search_author(author_name: str, limit: int = 10) -> list[TextContent]:
    """Search author information"""
    # Check cache
    cache_key = f"author:{author_name}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return [TextContent(type="text", text=cached["output"])]

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Search author
        encoded_name = quote(author_name)
        url = f"{SEMANTIC_SCHOLAR_API}/author/search?query={encoded_name}&limit={limit}&fields=name,url,paperCount,citationCount,hIndex"
        response = await client.get(url)

        if response.status_code != 200:
            return [TextContent(type="text", text=f"Failed to search author: HTTP {response.status_code}")]

        data = response.json()
        authors = data.get("data", [])

        if not authors:
            return [TextContent(type="text", text=f"Author not found: {author_name}")]

        output = f"# Author Search Results: \"{author_name}\"\n\n"
        output += f"**Found {len(authors)} authors**\n\n"

        for i, author in enumerate(authors, 1):
            name = author.get("name", "N/A")
            paper_count = author.get("paperCount", 0)
            citation_count = author.get("citationCount", 0)
            h_index = author.get("hIndex", 0)
            url = author.get("url", "")

            output += f"## [{i}] {name}\n"
            output += f"- **Papers**: {paper_count}\n"
            output += f"- **Citations**: {citation_count}\n"
            output += f"- **H-Index**: {h_index}\n"
            if url:
                output += f"- **Homepage**: {url}\n"
            output += "\n"

        set_cache(cache_key, {"output": output})
        return [TextContent(type="text", text=output)]


async def get_citation_formats(
    doi: str | None = None,
    paper_id: str | None = None,
    format: str = "all",
) -> list[TextContent]:
    """Get multiple citation formats"""
    # Get paper info
    title = None
    authors = []
    year = None
    venue = None
    doi_found = doi

    if doi:
        doi = doi.strip()
        if doi.startswith("doi:"):
            doi = doi[4:]
        if doi.startswith("https://doi.org/"):
            doi = doi[16:]

        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{CROSSREF_API}/{doi}"
            response = await client.get(url)

            if response.status_code == 200:
                data = response.json()
                work = data.get("message", {})
                title = work.get("title", ["N/A"])[0]
                authors = [
                    f"{a.get('given', '')} {a.get('family', '')}".strip()
                    for a in work.get("author", [])
                ]
                year = work.get("published-print", {}).get("date-parts", [[None]])[0][0]
                year = year or work.get("published-online", {}).get("date-parts", [[None]])[0][0]
                venue = work.get("container-title", [""])[0] or None
                doi_found = doi

    elif paper_id:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{SEMANTIC_SCHOLAR_API}/paper/{paper_id}?fields=title,authors,year,venue,doi"
            response = await client.get(url)

            if response.status_code == 200:
                data = response.json()
                title = data.get("title")
                authors = [a.get("name", "") for a in data.get("authors", [])]
                year = data.get("year")
                venue = data.get("venue")
                doi_found = data.get("doi")

    if not title:
        return [TextContent(type="text", text="Please provide a valid DOI or paper_id")]

    # Generate citation formats
    output = f"# Citation Formats\n\n"
    output += f"**Paper**: {title}\n\n"

    # Build author string
    if authors:
        if len(authors) <= 2:
            author_str = " & ".join(authors)
        else:
            author_str = f"{authors[0]} et al."
        all_authors = ", ".join(authors)
    else:
        author_str = "Unknown"
        all_authors = "Unknown"

    year_str = str(year) if year else "n.d."

    # APA format
    if format in ["all", "apa"]:
        apa = f"{all_authors} ({year_str}). {title}"
        if venue:
            apa += f". {venue}"
        if doi_found:
            apa += f". https://doi.org/{doi_found}"
        output += f"## APA\n```\n{apa}\n```\n\n"

    # MLA format
    if format in ["all", "mla"]:
        if authors:
            first_author = authors[0].split()[-1] + ", " + " ".join(authors[0].split()[:-1]) if len(authors[0].split()) > 1 else authors[0]
            if len(authors) > 1:
                mla = f'{first_author}, et al. "{title}"'
            else:
                mla = f'{first_author}. "{title}"'
        else:
            mla = f'"{title}"'
        if venue:
            mla += f". {venue}"
        if year:
            mla += f", {year_str}"
        output += f"## MLA\n```\n{mla}\n```\n\n"

    # Chicago format
    if format in ["all", "chicago"]:
        chicago = f'{all_authors}. "{title}"'
        if venue:
            chicago += f" {venue}"
        if year:
            chicago += f" ({year_str})"
        output += f"## Chicago\n```\n{chicago}\n```\n\n"

    # IEEE format
    if format in ["all", "ieee"]:
        ieee = f'{all_authors}, "{title}"'
        if venue:
            ieee += f", {venue}"
        if year:
            ieee += f", {year_str}"
        output += f"## IEEE\n```\n{ieee}\n```\n\n"

    # Vancouver format
    if format in ["all", "vancouver"]:
        van = f"{all_authors}. {title}"
        if venue:
            van += f". {venue}"
        if year:
            van += f". {year_str}"
        if doi_found:
            van += f". doi:{doi_found}"
        output += f"## Vancouver\n```\n{van}\n```\n\n"

    # BibTeX format
    if format in ["all"]:
        bibtex = generate_bibtex(title, authors, year, venue, doi_found)
        output += f"## BibTeX\n```bibtex\n{bibtex}\n```\n"

    return [TextContent(type="text", text=output)]


async def run_server():
    """Run MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main():
    """Start MCP Server"""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
