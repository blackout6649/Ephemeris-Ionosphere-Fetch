import shutil
import os


def convert_to_bin(input_file):
    """
    Convert any file into a raw .bin file (just copies the bytes).
    """
    # Create output filename with .bin extension
    base, _ = os.path.splitext(input_file)
    output_file = base + ".bin"


    # Copy file as-is
    shutil.copyfile(input_file, output_file)
    print(f"Converted: {input_file} -> {output_file}")


# Example usage
if __name__ == "__main__":
    input_path = "igsg0010.20i"  # Change to your file path
    convert_to_bin(input_path)
