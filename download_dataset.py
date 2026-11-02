from datasets import load_dataset

def main():
    print("Downloading SROIE dataset from Hugging Face...")

    dataset = load_dataset("jsdnrs/ICDAR2019-SROIE")

    print("\nDataset information:")
    print(dataset)

    dataset.save_to_disk("data/sroie")

    print("\nSROIE dataset saved to data/sroie")

    for split, split_data in dataset.items():
        print(f"{split}: {len(split_data)} examples")
        print("Columns:", split_data.column_names)

    sample = next(iter(dataset.values()))[0]
    print("\nSample keys:", sample.keys())
    print("Sample company:", sample.get("entities", {}).get("company"))
    print("Sample entities:", sample.get("entities"))

if __name__ == "__main__":
    main()