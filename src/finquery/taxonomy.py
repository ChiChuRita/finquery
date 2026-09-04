"""The default category taxonomy seeded into every new profile.

One level deep: a category owns subcategories. `Unknown` is a real category a human assigns
when a transaction fits nothing, so it ships without subcategories and automation never
produces it. The absence of a category is `Needs review`, not a category.
"""

DEFAULT_TAXONOMY: dict[str, tuple[str, ...]] = {
    "Income": ("Salary", "Interest", "Refunds", "Other income"),
    "Housing": ("Rent", "Electricity", "Heating", "Internet"),
    "Groceries": ("Supermarket", "Bakery", "Drugstore"),
    "Dining": ("Restaurant", "Cafe", "Takeaway", "Delivery"),
    "Transport": ("Public transport", "Fuel", "Ride hailing", "Car"),
    "Shopping": ("Clothing", "Electronics", "Home", "Online marketplace"),
    "Subscriptions": ("Streaming", "Software", "Music", "News"),
    "Health": ("Pharmacy", "Doctor", "Fitness"),
    "Insurance": ("Health insurance", "Liability", "Household"),
    "Communication": ("Mobile", "Landline"),
    "Leisure": ("Travel", "Events", "Hobbies", "Books"),
    "Education": ("Tuition", "Courses", "Supplies"),
    "Cash": ("Cash withdrawal",),
    "Transfers": ("Savings", "Friends and family", "Internal"),
    "Fees and taxes": ("Bank fees", "Taxes"),
    "Unknown": (),
}
