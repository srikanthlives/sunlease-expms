import { useEffect, useState } from "react";
import client from "../api/client";

export function useMasters() {
  const [data, setData] = useState({
    projects: [], vendors: [], categories: [], accounts: [], employees: [], subCategories: [],
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      client.get("/projects"),
      client.get("/vendors"),
      client.get("/categories"),
      client.get("/accounts"),
      client.get("/employees"),
    ])
      .then(([projects, vendors, categories, accounts, employees]) => {
        setData((d) => ({
          ...d,
          projects: projects.data, vendors: vendors.data, categories: categories.data,
          accounts: accounts.data, employees: employees.data,
        }));
        // Sub-categories only have a per-category list endpoint - flatten
        // across every category so consumers (e.g. edit forms) can filter
        // client-side by category_id without extra round-trips per edit.
        Promise.all(categories.data.map((c) => client.get(`/categories/${c.id}/sub-categories`)))
          .then((results) => {
            setData((d) => ({ ...d, subCategories: results.flatMap((r) => r.data) }));
          });
      })
      .finally(() => setLoading(false));
  }, []);

  return { ...data, loading };
}
