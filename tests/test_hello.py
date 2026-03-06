[
    'sys.executable, str(script_path)],\n        capture_output=True,\n        text=True\n    )\n    \n    # Verify the script executed successfully\n    assert result.returncode == 0, f"Script failed with return code {result.returncode}"\n    \n    # Verify the output\n    expected_output = "hello from opencode serve',
    "assert result.stdout == expected_output, f",
    "Expected '{expected_output}', but got '{result.stdout}'\"\n\n\ndef test_hello_script_exists():\n    \"",
    'Test that hello.py file exists in project root."',
    '\n    script_path = Path(__file__).parent.parent / "hello.py',
    'assert script_path.exists(), "hello.py file should exist in project root"\n\n\ndef test_hello_script_content():\n    "',
    'Test that hello.py contains the expected content."',
    '\n    script_path = Path(__file__).parent.parent / "hello.py',
    "with open(script_path, 'r') as f:\n        content = f.read()\n        \n    # Check that it contains the print statement\n    assert 'print(\"hello from opencode serve",
    " in content",
]
