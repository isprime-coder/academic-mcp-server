# Academic MCP Server

Academic research assistant for Claude Code CLI - provides paper search, DOI verification, citation analysis, BibTeX generation, and GitHub integration.

> ⚠️ **This is my first open source project**, there may be bugs and some features may not work perfectly. If you find any issues, feel free to submit an Issue or PR!

## What is Academic MCP Server?

This is an **academic research assistant** that helps you:
- Search academic papers (Semantic Scholar + arXiv)
- Verify DOI authenticity
- Generate BibTeX/APA/MLA citations
- Get paper PDF download links
- View citation relationships
- Find similar papers
- Read GitHub repository documentation

Mainly used for **paper writing, literature review, and academic research** to quickly get the information you need.

## Features

| Tool | Description |
|------|------------|
| `search_papers` | Search academic papers (Semantic Scholar + arXiv) |
| `get_paper_details` | Get paper details |
| `verify_doi` | Verify DOI authenticity and get metadata |
| `get_bibtex` | Generate BibTeX citation format |
| `get_citation_formats` | Get multiple citation formats (APA/MLA/Chicago/IEEE/Vancouver) |
| `get_pdf_links` | Get paper PDF download links |
| `get_citations` | Get citation relationships |
| `get_similar_papers` | Get similar paper recommendations |
| `search_author` | Search author information |
| `fetch_github_readme` | Read GitHub documentation |
| `search_github` | GitHub repo/code search (requires GitHub CLI) |
| `get_github_repo_info` | Get GitHub repository details (requires GitHub CLI) |

## Platform Support

- ✅ Windows 10/11
- ✅ macOS
- ✅ Linux

The project **can be placed anywhere** since it uses relative paths for the cache directory. Just update the path in your Claude config file when moving the project.

## Installation

```bash
# Install dependencies
pip install mcp httpx arxiv

# Optional: Install GitHub CLI for GitHub search features
# Windows: winget install GitHub.cli
# Or visit https://cli.github.com/
```

## Configuration

Add the following to your Claude Code CLI config file:

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "academic-server": {
      "command": "python",
      "args": ["path/to/academic-mcp-server/run_server.py"]
    }
  }
}
```

> Note: Adjust `command` and `args` based on your Python installation path and project location.

## Usage Examples

### Search Papers

```
Search for "attention is all you need"
Search for papers about vision transformer from 2020-2024
```

### Generate Citations

```
Generate BibTeX for this paper: 10.48550/arXiv.1706.03762
Get APA citation for this paper
Generate multiple citation formats for me to choose
```

### Verify DOI

```
Verify this DOI: 10.1038/nature14539
Check if this paper's citation format is correct
```

### Get PDF

```
Get the PDF link for this arXiv paper: 2301.07001
Does this paper have an open access PDF?
```

### Citation Analysis

```
See which papers cite "Attention Is All You Need"
What references does this paper cite?
Find similar research to this paper
```

### Author Search

```
Search for author Yann LeCun
How many papers and citations does this author have?
```

### GitHub Integration

```
Search for MCP server projects on GitHub
Read huggingface/transformers README
View PyTorch repository details
```

## API Reference

### search_papers

Search academic papers.

**Parameters:**
- `query` (required): Search keyword
- `limit` (optional): Number of results, default 5
- `year_range` (optional): Year range, e.g., "2020-2024"
- `source` (optional): Data source - "all" (default), "semantic", "arxiv"

**Features:**
- Auto-caches search results
- Returns PDF links (if open access)

### get_paper_details

Get paper details.

**Parameters:**
- `paper_id` (required): Paper ID
- `source` (optional): "semantic" or "arxiv"

### verify_doi

Verify DOI and get metadata.

**Parameters:**
- `doi` (required): DOI identifier

### get_bibtex

Generate BibTeX citation.

**Parameters:**
- `doi` (optional): DOI identifier
- `paper_id` (optional): Semantic Scholar paper ID
- `paper_title` (optional): Paper title (for search)

### get_citation_formats

Get multiple citation formats.

**Parameters:**
- `doi` (optional): DOI identifier
- `paper_id` (optional): Semantic Scholar paper ID
- `format` (optional): Citation format - "all" (default), "apa", "mla", "chicago", "ieee", "vancouver"

### get_pdf_links

Get paper PDF download links.

**Parameters:**
- `paper_id` (required): Paper ID
- `source` (optional): "arxiv" (default) or "semantic"

### get_citations

Get citation relationships.

**Parameters:**
- `paper_id` (required): Semantic Scholar paper ID
- `direction` (optional): "forward" (cited by) or "backward" (cites)
- `limit` (optional): Number of results, default 10

### get_similar_papers

Get similar paper recommendations.

**Parameters:**
- `paper_id` (required): Semantic Scholar paper ID
- `limit` (optional): Number of results, default 5

### search_author

Search author information.

**Parameters:**
- `author_name` (required): Author name
- `limit` (optional): Number of results, default 10

### fetch_github_readme

Get GitHub repository README.

**Parameters:**
- `repo_url` (required): GitHub URL or "owner/repo" format

### search_github

GitHub search (requires GitHub CLI).

**Parameters:**
- `query` (required): Search keyword
- `type` (optional): "repos" (default) or "code"
- `limit` (optional): Number of results, default 10

### get_github_repo_info

Get GitHub repository details (requires GitHub CLI).

**Parameters:**
- `repo` (required): Repository name, e.g., "huggingface/transformers"

## Features

### Local Cache

Search results and paper metadata are cached locally to reduce API requests:
- Cache location: `Cache/` folder in project directory
- Cache expiry: 24 hours
- Auto-created database: `Cache/cache.db`

### Request Retry

Automatic retry on network instability:
- Max retries: 3
- Retry strategy: Exponential backoff

### GitHub CLI Integration

Using GitHub CLI provides better GitHub access:
- Search repositories and code
- Get repository details
- No dependency on raw.githubusercontent.com

**Configure GitHub CLI:**
```bash
# Login
gh auth login

# Check status
gh auth status
```

## Notes

### Semantic Scholar Rate Limit

- Free tier: 100 requests per 5 minutes
- For higher limits: [Apply for API Key](https://www.semanticscholar.org/product/api)
- Wait a few minutes when hitting 429 errors

### Network Requirements

| Service | Status |
|--------|:------:|
| Semantic Scholar API | ✅ Stable |
| arXiv API | ✅ Stable |
| Crossref API (DOI) | ✅ Stable |
| GitHub API | ✅ Stable |
| GitHub Raw | ⚠️ May be unstable |

This project prioritizes stable academic APIs:
- Semantic Scholar - Paper search & citation analysis
- arXiv - Preprint papers
- Crossref - DOI verification

## Testing

```bash
cd path/to/academic-mcp-server
python test_server.py
```

## Project Structure

```
academic-mcp-server/
├── pyproject.toml       # Project config
├── run_server.py        # Startup script
├── test_server.py       # Test script
├── README.md            # Documentation
├─�� LICENSE            # MIT License
├── .gitignore          # Git ignore rules
├── Cache/              # Local cache (auto-created)
│   └── cache.db        # SQLite cache database
└── src/
    └── academic_mcp/
        ├── __init__.py
        └── server.py    # Core implementation
```

## FAQ

**Q: Semantic Scholar search returns empty results?**

A: You may have hit the rate limit. Wait a few minutes and try again. The error will show "429 Too Many Requests".

**Q: DOI verification failed?**

A: Make sure the DOI format is correct, e.g., `10.1038/nature14539`. Do not add `https://doi.org/` prefix.

**Q: GitHub CLI shows not logged in?**

A: Run `gh auth login` and follow the prompts to login to GitHub.com via HTTPS and browser.

**Q: Does cache take up a lot of space?**

A: Cache only stores paper metadata, not PDF files. Usually just a few MB. Cache expires after 24 hours.

## Dependencies

- Python >= 3.10
- mcp >= 1.0.0
- httpx >= 0.27.0
- arxiv >= 2.1.0
- GitHub CLI (optional, for GitHub search features)

## About This Project

This is my **first open source project**. If you find any bugs or have suggestions, welcome to:

- Submit [Issue](https://github.com/isprime-coder/academic-mcp-server/issues)
- Submit [PR](https://github.com/isprime-coder/academic-mcp-server/pulls)

Due to limited time and experience, the project may have shortcomings. Thank you for your understanding and support!

## License

MIT License - See [LICENSE](LICENSE) file for details.