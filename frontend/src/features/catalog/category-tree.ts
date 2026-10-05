import type { Category } from "@/lib/api/types";

/** Categorías en orden de árbol (padre y luego sus hijas), con profundidad 0 o 1. */
export function categoryTree(categories: Category[]): { category: Category; depth: number }[] {
  const roots = categories.filter((c) => !c.parent_id);
  return roots.flatMap((root) => [
    { category: root, depth: 0 },
    ...categories.filter((c) => c.parent_id === root.id).map((category) => ({ category, depth: 1 })),
  ]);
}

export function categoryOptions(categories: Category[]): { value: string; label: string }[] {
  return categoryTree(categories).map(({ category, depth }) => ({
    value: category.id,
    label: depth ? `   ${category.name}` : category.name,
  }));
}
