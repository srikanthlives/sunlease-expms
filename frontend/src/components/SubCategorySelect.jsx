import { useEffect, useState } from "react";
import client from "../api/client";
import { Select } from "./ui";

/** Sub-category select scoped to a chosen Expense Head (category). Fetches
 * fresh whenever categoryId changes since sub-categories aren't in useMasters. */
export default function SubCategorySelect({ categoryId, value, onChange, label = "Sub-Category" }) {
  const [subCategories, setSubCategories] = useState([]);

  useEffect(() => {
    if (!categoryId) { setSubCategories([]); return; }
    client.get(`/categories/${categoryId}/sub-categories`).then((res) => setSubCategories(res.data));
  }, [categoryId]);

  return (
    <Select label={label} value={value} onChange={(e) => onChange(e.target.value)} disabled={!categoryId}>
      <option value="">— none —</option>
      {subCategories.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
    </Select>
  );
}
