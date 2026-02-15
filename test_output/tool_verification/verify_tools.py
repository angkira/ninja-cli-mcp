#!/usr/bin/env python3
"""
Verify all 6 ninja-coder MCP tools are properly registered.
"""

import sys
from pathlib import Path

# Setup path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

def main():
    print("\n" + "="*70)
    print("NINJA-CODER MCP TOOLS VERIFICATION")
    print("Testing tool registration after binary path auto-detection fix")
    print("="*70)
    
    try:
        # Import the TOOLS list from server
        from ninja_coder.server import TOOLS
        
        # Get tool names
        tool_names = [t.name for t in TOOLS]
        
        print(f"\nFound {len(TOOLS)} registered tools in the MCP server\n")
        
        # Define the 6 tools to test
        test_cases = [
            {
                "name": "coder_simple_task",
                "test": "Create a simple hello.py file with a greeting function",
                "skip": False
            },
            {
                "name": "coder_execute_plan_sequential",
                "test": "Two-step task: create math.py with add, then multiply",
                "skip": False
            },
            {
                "name": "coder_execute_plan_parallel",
                "test": "Two independent files: string_helper.py and number_helper.py",
                "skip": False
            },
            {
                "name": "coder_query_logs",
                "test": "Query recent logs to verify logging works",
                "skip": False
            },
            {
                "name": "coder_get_agents",
                "test": "Get list of available specialized agents",
                "skip": False
            },
            {
                "name": "coder_multi_agent_task",
                "test": "Complex multi-agent orchestration (SKIPPED - requires setup)",
                "skip": True
            }
        ]
        
        print("="*70)
        print("TOOL VERIFICATION RESULTS")
        print("="*70)
        
        results = []
        
        for i, test_case in enumerate(test_cases, 1):
            tool_name = test_case["name"]
            test_desc = test_case["test"]
            skip = test_case["skip"]
            
            if tool_name in tool_names:
                # Find the tool
                tool = next(t for t in TOOLS if t.name == tool_name)
                
                if skip:
                    status = "⏭️  SKIP"
                    result = "SKIP"
                else:
                    status = "✅ PASS"
                    result = "PASS"
                
                results.append({
                    "tool": tool_name,
                    "status": result,
                    "test": test_desc
                })
                
                print(f"\n{i}. {status} {tool_name}")
                print(f"   Test: {test_desc}")
                
                # Show description snippet
                desc = tool.description.split('\n')[0][:100]
                if len(tool.description.split('\n')[0]) > 100:
                    desc += "..."
                print(f"   Description: {desc}")
                
            else:
                status = "❌ FAIL"
                results.append({
                    "tool": tool_name,
                    "status": "FAIL",
                    "test": test_desc,
                    "error": "Tool not registered"
                })
                print(f"\n{i}. {status} {tool_name}")
                print(f"   Test: {test_desc}")
                print(f"   ERROR: Tool not found in registered tools")
        
        # Print summary
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        
        passed = sum(1 for r in results if r['status'] == 'PASS')
        failed = sum(1 for r in results if r['status'] == 'FAIL')
        skipped = sum(1 for r in results if r['status'] == 'SKIP')
        
        print(f"\nTotal: {len(test_cases)} tools tested")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⏭️  Skipped: {skipped}")
        
        if failed > 0:
            print(f"\n❌ {failed} tool(s) failed registration check")
            print("\n" + "="*70 + "\n")
            return 1
        else:
            print(f"\n✅ All required tools are properly registered!")
            
        print("\n" + "="*70)
        print("VERIFICATION NOTES")
        print("="*70)
        print("""
This test verifies that all 6 ninja-coder MCP tools are properly 
registered in the server after the binary path auto-detection fix.

WHAT WAS TESTED:
- Tool registration in MCP server
- Tool metadata (name, description)
- Availability through MCP protocol

WHAT WAS NOT TESTED (requires MCP client):
- Actual tool execution
- File creation/modification
- Error handling
- Multi-agent orchestration

The binary path auto-detection ensures these tools can find and 
execute the ninja-coder binary when invoked through MCP clients.

To test actual execution, use an MCP client like:
  - Claude Desktop (MCP client)
  - npx @modelcontextprotocol/inspector
  - Custom MCP client implementation
        """)
        print("="*70 + "\n")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ ERROR: Failed to verify tools")
        print(f"   {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
