# MCP-GMX-VMD

MCP-GMX-VMD is a service that integrates GROMACS molecular dynamics simulations with VMD (Visual Molecular Dynamics) visualization through a microservice architecture. This tool facilitates molecular dynamics simulation setup, execution, analysis, and visualization.

## Features

- **Molecular Dynamics Simulations**: Setup and run GROMACS simulations with an easy-to-use interface
- **Trajectory Analysis**: Analyze simulation trajectories (RMSD, RMSF, etc.)
- **3D Visualization**: Visualize molecular structures and simulation trajectories using VMD
- **Custom Workflow Directories**: Create and manage simulation workflows in user-specified directories
- **Modular Architecture**: Built on MCP (Microservice Communication Protocol) for flexible integration with other tools

## Prerequisites

- Python 3.9+
- GROMACS (installed and accessible in PATH)
- VMD (Visual Molecular Dynamics, installed and accessible in PATH)
- (Optional) Python VMD module for enhanced visualization capabilities

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/mcp-gmx-vmd.git
   cd mcp-gmx-vmd
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Install the package (development mode):

   ```bash
   pip install -e .
   ```

## Configuration

The service uses a configuration file (`config.json`) for VMD path, search paths, and other settings. If this file doesn't exist, create one with the following structure:

```json
{
  "vmd": {
    "path": "/path/to/vmd/executable",
    "search_paths": ["/path/to/search"]
  },
  "gmx": {
    "path": "/path/to/gromacs/executable"
  }
}
```

For macOS users, the VMD path is typically:

```
/Applications/VMD.app/Contents/MacOS/startup.command
```

## Starting the Server

To start the MCP-GMX-VMD server:

```bash
python mcp_server.py
```

The service will start and listen for requests.

## Usage Examples

### Creating a simulation workflow:

```python
import requests

# Create a new workflow
response = requests.get(
    "http://localhost:8000/gmx-vmd://workflow/create?name=my_simulation"
)
workflow_id = response.json()["workflow_id"]

# Prepare a simulation with custom directory
custom_dir = "/path/to/custom/directory"
response = requests.get(
    f"http://localhost:8000/gmx-vmd://simulation/prepare?workflow_id={workflow_id}&pdb_file=protein.pdb&workspace_dir={custom_dir}"
)
```

### Analyzing trajectories:

```python
# Analyze RMSD
analysis_params = {
    "analysis_type": "rmsd",
    "trajectory_file": "md/md.xtc",
    "structure_file": "md/md.gro",
    "selection": "protein",
    "output_prefix": "rmsd_analysis"
}
response = requests.get(
    f"http://localhost:8000/gmx-vmd://analysis/trajectory?workflow_id={workflow_id}&params={json.dumps(analysis_params)}"
)
```

### Visualizing structures:

```python
# Load and visualize trajectory
response = requests.get(
    f"http://localhost:8000/gmx-vmd://visualization/load-trajectory?workflow_id={workflow_id}&trajectory_file=md/md.xtc&structure_file=md/md.gro"
)
```

## LLM Integration

This service can be integrated with LLM assistants like Claude or used with Cursor IDE for a more interactive experience. The integration allows you to perform molecular simulations and analysis directly through natural language commands.

### Connect to the MCP Server

1. Copy the below JSON and replace the path placeholders with your actual system paths:

```json
{
  "mcpServers": {
    "gmx_vmd": {
      "command": "{{PATH_TO_UV}}",
      "args": [
        "--directory",
        "{PATH_TO_SRC}/mcp-gmx-vmd",
        "run",
        "mcp",
        "run",
        "mcp_server.py"
      ],
      "env": {
        "PYTHONPATH": "{PATH_TO_SRC}/mcp-gmx-vmd",
        "MCP_DEBUG": "1",
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

2. Save the configuration file to the appropriate location:
   - **For Claude Desktop**: Save as `claude_desktop_config.json` in:
     `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **For Cursor IDE**: Save as `mcp.json` in:
     `~/.cursor/mcp.json`

3. Restart your application (Claude Desktop or Cursor)
   - For Claude Desktop, you should now see GMX-VMD as an available integration
   - For Cursor, the integration will be available after restart

### Using MCP-GMX-VMD with LLMs

Once configured, you can interact with the MCP-GMX-VMD service through natural language:

- "Set up a protein simulation in water environment"
- "Analyze the RMSD of my protein trajectory"
- "Visualize this protein structure showing secondary structure"
- "Calculate hydrogen bonds in my MD trajectory"

The LLM will translate your requests into appropriate API calls to the MCP-GMX-VMD service.

## Advanced Configuration

### Custom Workflow Directories

To create workflows in custom directories, specify the `workspace_dir` parameter when creating a workflow:

```python
response = requests.get(
    f"http://localhost:8000/gmx-vmd://workflow/create?name=custom_workflow&workspace_dir=/path/to/custom/directory"
)
```

### VMD Visualization Templates

The service provides several built-in visualization templates for common tasks. You can apply these templates using:

```python
response = requests.get(
    f"http://localhost:8000/gmx-vmd://visualization/apply-template?workflow_id={workflow_id}&template_name=protein_cartoon"
)
```

## Troubleshooting

### VMD Display Issues

If VMD GUI closes immediately after launch, try using one of these approaches:

1. Launch VMD in a separate terminal window (service default behavior)
2. Use `vmd -dispdev text` for command-line operation without GUI
3. Check VMD installation and permissions

### Permission Issues

If you encounter permission issues with custom directories:

```bash
# Set appropriate permissions for the directory
chmod -R 755 /path/to/your/custom/directory
```

## License

[MIT License](LICENSE)

## YouTube Overview
[![IMAGE ALT TEXT HERE](https://img.youtube.com/vi/ShQnOVxsrBA/0.jpg)](https://www.youtube.com/watch?v=ShQnOVxsrBA)

## Acknowledgments

- VMD is developed by the Theoretical and Computational Biophysics Group at the University of Illinois at Urbana-Champaign
- GROMACS is a versatile package for molecular dynamics simulation
- MCP (Model Context Protocol ) provides the underlying communication framework
