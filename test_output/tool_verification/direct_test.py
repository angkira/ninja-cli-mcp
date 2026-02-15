#!/usr/bin/env python3
"""
Direct test of MCP tools by importing and checking their registration.
"""

import sys
from pathlib import Path
import asyncio

# Setup path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

async def run_verification():
    print("\n" + "="*60)
    print("NINJA-CODER MCP TOOLS VERIFICATION")
    print("="*60)
    
    try:
        # Import the server module
        from ninja_coder.server import create_server
        
        # Create server instance
        print("\n[1/6] Creating MCP server instance...")
        server = create_server()
        print("    ✅ Server created successfully")
        
        # Get list of tools - it's async
        print("\n[2/6] Retrieving registered tools...")
        tools_response = await server.list_tools()
        tools = tools_response.tools
        tool_names = [t.name for t in tools]
        print(f"    ✅ Found {len(tools)} registered tools")
        
        # Define expected tools
        expected_tools = [
            "coder_simple_task",
            "coder_execute_plan_sequential", 
            "coder_execute_plan_parallel",
            "coder_query_logs",
            "coder_get_agents",
            "coder_multi_agent_task"
        ]
        
        print("\n" + "="*60)
        print("TOOL REGISTRATION VERIFICATION")
        print("="*60)
        
        results = []
        
        for tool_name in expected_tools:
            if tool_name in tool_names:
                tool = next(t for t in tools if t.name == tool_name)
                
                # Get tool description
                desc = tool.description[:80] + "..." if len(tool.description) > 80 else tool.description
                
                results.append({
                    "tool": tool_name,
                    "status": "PASS",
                    "description": desc
                })
                
                print(f"\n✅ {tool_name}")
                print(f"   Description: {desc}")
                
                # Special handling for multi_agent_task
                if tool_name == "coder_multi_agent_task":
                    print(f"   Note: Skipped execution test (requires complex setup)")
            else:
                results.append({
                    "tool": tool_name,
                    "status": "FAIL",
                    "description": "Tool not registered"
                })
                print(f"\n❌ {tool_name}")
                print(f"   ERROR: Tool not found in registered tools")
        
        # Print summary
        print("\n" + "="*60)
        print("VERIFICATION SUMMARY")
        print("="*60)
        
        passed = sum(1 for r in results if r['status'] == 'PASS')
        failed = sum(1 for r in results if r['status'] == 'FAIL')
        
        print(f"\nResults: {passed}/{len(expected_tools)} tools registered")
        
        if failed > 0:
            print(f"❌ {failed} tools failed registration check")
            return 1
        else:
            print(f"✅ All tools registered successfully")
            
        print("\n" + "="*60)
        print("ADDITIONAL VERIFICATION NOTES")
        print("="*60)
        print("""
The following tests verify tool REGISTRATION only.
For full functionality tests, the tools need to be invoked through MCP protocol.

MANUAL TEST RECOMMENDATIONS:
1. coder_simple_task - Create hello.py: Use MCP client to call tool
2. coder_execute_plan_sequential - Sequential steps: Use MCP client
3. coder_execute_plan_parallel - Parallel tasks: Use MCP client  
4. coder_query_logs - Query logs: Use MCP client
5. coder_get_agents - List agents: Use MCP client
6. coder_multi_agent_task - Complex workflow: Requires full setup

The binary path auto-detection fix ensures the tools can execute
when called through the MCP protocol.
""")
        print("="*60 + "\n")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ ERROR: Failed to verify tools")
        print(f"   {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

def main():
    return asyncio.run(run_verification())

if __name__ == "__main__":
    sys.exit(main())
