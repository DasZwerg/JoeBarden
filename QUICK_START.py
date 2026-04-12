#!/usr/bin/env python3
"""
Quick Start Guide for the Multi-Agent System
Run this file to see a simple demonstration of the agent system.
"""

import asyncio
import logging
from agent_system_demo import ProjectManager

async def quick_demo():
    """Quick demonstration of the agent system."""
    print("🚀 Multi-Agent System Quick Start\n")
    
    # Initialize the project manager
    project_manager = ProjectManager()
    await project_manager.initialize()
    
    try:
        # Example: Analyze and improve a simple function
        sample_code = '''
def process_data(data):
    """Process a list of numbers."""
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    return result
'''
        
        print("📊 Analyzing code...")
        analysis = await project_manager.analyze_existing_code(sample_code, "process_data.py")
        print(f"✅ Analysis completed: {analysis.get('status', 'unknown')}")
        
        # Example: Generate an improved version
        print("\n🔧 Generating improved implementation...")
        improved_spec = {
            "type": "function",
            "function_name": "process_data_enhanced",
            "description": "Enhanced data processing with error handling and type hints",
            "parameters": [
                {"name": "data", "type": "List[Union[int, float]]", "description": "List of numbers to process"}
            ],
            "return_type": "List[Union[int, float]]"
        }
        
        implementation = await project_manager.generate_implementation(improved_spec)
        if "implementation" in implementation:
            print("✅ Generated improved function:")
            print(implementation["implementation"])
        
        # Example: Create comprehensive tests
        print("\n🧪 Creating test suite...")
        tests = await project_manager.create_test_suite(
            implementation.get("implementation", ""), 
            "unit_test"
        )
        print(f"✅ Test suite created: {tests.get('status', 'unknown')}")
        
        # Show system status
        print("\n📈 System Status:")
        status = project_manager.get_project_status()
        print(f"   Active agents: {status['system_status']['coordinator']['registered_agents']}")
        print(f"   Messages processed: {status['system_status']['message_broker']['total_messages']}")
        
    finally:
        await project_manager.shutdown()
    
    print("\n🎉 Quick start completed! Check README.md for more details.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)  # Reduce log noise for demo
    asyncio.run(quick_demo())
