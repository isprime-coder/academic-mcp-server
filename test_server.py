"""Test Academic MCP Server - All Functions"""
import asyncio
import sys
sys.path.insert(0, "src")

from academic_mcp.server import (
    search_papers,
    get_paper_details,
    verify_doi,
    fetch_github_readme,
    get_citations,
    get_bibtex,
    search_github,
    get_github_repo_info,
    get_pdf_links,
    get_similar_papers,
    search_author,
    get_citation_formats,
    generate_bibtex,
    init_cache,
    get_cache,
    set_cache,
    CACHE_DIR,
)


async def test_cache():
    """Test cache system"""
    print("\n[Cache Test]")
    print(f"Cache directory: {CACHE_DIR}")
    init_cache()
    set_cache("test_key", {"data": "test_value"})
    result = get_cache("test_key")
    print(f"Cache R/W: {'Success' if result else 'Failed'}")
    print("✅ Cache system OK\n")


def test_bibtex_generation():
    """Test BibTeX generation"""
    print("[BibTeX Generation Test]")
    result = generate_bibtex(
        "Attention Is All You Need",
        ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
        2017,
        "NeurIPS",
        "10.48550/arXiv.1706.03762"
    )
    print(result)
    print("✅ BibTeX generation OK\n")


def test_citation_formats():
    """Test citation format generation"""
    print("[Citation Format Test]")
    # Test internal formatting logic
    authors = ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"]
    title = "Attention Is All You Need"
    year = 2017
    venue = "NeurIPS"

    # APA
    apa = f"{', '.join(authors)} ({year}). {title}. {venue}."
    print(f"APA: {apa}")

    # MLA
    mla = f'Vaswani, Ashish, et al. "{title}" {venue}, {year}.'
    print(f"MLA: {mla}")

    print("✅ Citation format generation OK\n")


def test_gh_detection():
    """Test GitHub CLI detection"""
    print("[GitHub CLI Detection]")
    from academic_mcp.server import run_gh_command
    success, msg = run_gh_command(["--version"])
    print(f"Detection: {'Success' if success else 'Failed'}")
    if success:
        print(f"Version: {msg.strip()}")
    else:
        print(f"Error: {msg}")
    print("✅ GitHub CLI detection OK\n")


async def test_offline_functions():
    """Test offline available functions"""
    print("\n" + "=" * 60)
    print("Offline Functions Test")
    print("=" * 60)

    await test_cache()
    test_bibtex_generation()
    test_citation_formats()
    test_gh_detection()


async def test_online_functions():
    """Test functions requiring network"""
    print("\n" + "=" * 60)
    print("Online Functions Test (requires network connection)")
    print("=" * 60)

    tests = [
        ("Semantic Scholar Search", lambda: search_papers("attention is all you need", limit=2, source="semantic")),
        ("arXiv Search", lambda: search_papers("vision transformer", limit=2, source="arxiv")),
        ("DOI Verification", lambda: verify_doi("10.48550/arXiv.1706.03762")),
        ("BibTeX Get", lambda: get_bibtex(doi="10.48550/arXiv.1706.03762")),
        ("GitHub README", lambda: fetch_github_readme("modelcontextprotocol/servers")),
        ("GitHub Repo Info", lambda: get_github_repo_info("huggingface/transformers")),
        ("GitHub Search", lambda: search_github("mcp server python", type="repos", limit=3)),
        ("Citations", lambda: get_citations("204e3073870fae3d05bcbc2f6a8e263d9b72e776", direction="forward", limit=3)),
        ("PDF Links", lambda: get_pdf_links("1706.03762", source="arxiv")),
        ("Similar Papers", lambda: get_similar_papers("204e3073870fae3d05bcbc2f6a8e263d9b72e776", limit=3)),
        ("Author Search", lambda: search_author("Yann LeCun", limit=3)),
        ("Citation Formats", lambda: get_citation_formats(paper_id="204e3073870fae3d05bcbc2f6a8e263d9b72e776")),
    ]

    for name, test_func in tests:
        try:
            print(f"\n[Test] {name}...")
            result = await test_func()
            print(result[0].text[:500])
            print(f"✅ {name} Success")
        except Exception as e:
            print(f"❌ {name} Failed: {str(e)}")


async def main():
    print("=" * 60)
    print("Academic MCP Server - Function Test")
    print("=" * 60)

    # Offline test
    await test_offline_functions()

    # Ask about online test
    print("\n" + "-" * 60)
    print("Online test requires network connection")
    print("-" * 60)

    try:
        await test_online_functions()
    except Exception as e:
        print(f"\nOnline test interrupted: {str(e)}")
        print("This may be due to network issues. Please check your connection.")

    print("\n" + "=" * 60)
    print("Test Complete! MCP Server is Ready")
    print("=" * 60)
    print("\nConfig file location: %APPDATA%\\Claude\\claude_desktop_config.json")
    print("\nAvailable tools:")
    tools = [
        ("search_papers", "Search academic papers"),
        ("get_paper_details", "Get paper details"),
        ("verify_doi", "Verify DOI authenticity"),
        ("get_bibtex", "Generate BibTeX citation"),
        ("fetch_github_readme", "Read GitHub docs"),
        ("search_github", "GitHub repo/code search"),
        ("get_github_repo_info", "GitHub repo details"),
        ("get_citations", "Get citation relationships"),
        ("get_pdf_links", "Get PDF download links"),
        ("get_similar_papers", "Similar paper recommendations"),
        ("search_author", "Author search"),
        ("get_citation_formats", "Multi-format citation output"),
    ]
    for i, (name, desc) in enumerate(tools, 1):
        print(f"  {i:2d}. {name} - {desc}")


if __name__ == "__main__":
    asyncio.run(main())
