import type { Account } from "../../account/types";

interface Props {
  accounts: Account[];
  selected: string;
  onSelect: (last4: string) => void;
}

/** One button per account, by its name. Hidden when there's only one. */
export function AccountPicker({ accounts, selected, onSelect }: Props) {
  if (accounts.length < 2) return null;
  return (
    <div role="group" aria-label="Account" className="picker">
      {accounts.map((a) => (
        <button key={a.last4} type="button" aria-pressed={a.last4 === selected} onClick={() => onSelect(a.last4)}>
          {a.name}
        </button>
      ))}
    </div>
  );
}
