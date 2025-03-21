import subprocess
import sys

def run_command(command):
    """Run a shell command and print output"""
    print(f"Running: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)
    
    if result.stdout:
        print(result.stdout)
    
    if result.stderr:
        print(result.stderr)
    
    return result.returncode == 0

def fix_dependencies():
    """Fix numpy and pandas compatibility issues"""
    # Install setuptools and wheel first
    print("Step 1: Installing setuptools and wheel")
    run_command([sys.executable, "-m", "pip", "install", "setuptools", "wheel"])
    
    # Uninstall numpy and pandas
    print("\nStep 2: Uninstalling numpy and pandas")
    run_command([sys.executable, "-m", "pip", "uninstall", "-y", "pandas"])
    run_command([sys.executable, "-m", "pip", "uninstall", "-y", "numpy"])
    
    # Install numpy first
    print("\nStep 3: Installing numpy")
    numpy_success = run_command([sys.executable, "-m", "pip", "install", "numpy==1.26.0"])
    
    if not numpy_success:
        print("Failed to install numpy. Trying alternative version...")
        numpy_success = run_command([sys.executable, "-m", "pip", "install", "numpy==1.25.2"])
    
    if not numpy_success:
        print("ERROR: Failed to install numpy. Please try manually installing a compatible version.")
        return False
    
    # Install pandas
    print("\nStep 4: Installing pandas")
    pandas_success = run_command([sys.executable, "-m", "pip", "install", "pandas==2.0.3"])
    
    if not pandas_success:
        print("Failed to install pandas. Trying alternative version...")
        pandas_success = run_command([sys.executable, "-m", "pip", "install", "pandas==1.5.3"])
    
    if not pandas_success:
        print("ERROR: Failed to install pandas. Please try manually installing a compatible version.")
        return False
    
    print("\nStep 5: Verifying installations")
    run_command([sys.executable, "-c", "import numpy; print(f'NumPy version: {numpy.__version__}')"])
    run_command([sys.executable, "-c", "import pandas; print(f'Pandas version: {pandas.__version__}')"])
    
    print("\nDependencies fixed successfully! You can now run the application.")
    return True

if __name__ == "__main__":
    fix_dependencies() 