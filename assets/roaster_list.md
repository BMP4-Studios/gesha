# MVP
- [ ] the math for the per 100g doesn't work if there's less than 100g
- [ ] the free shipping line says "Estimated free-shipping threshold: $60.00 (live policy page)" -- it should clearly say whether it's estimated or fetched lol, not both

# NICE TO HAVE
- [ ] would be useful to have the opposite of gesha cart, like gesha non-cart lol, where it lists the coffees that were excluded and the reason why
      and/or, when you go "gesha cart roaster", it should show both a cart of coffees included and those excluded, so run both commands
- [ ] gesha roaster should run the scrape, the list, and the cart
- [ ] would be cool to either hardcode some keywords to avoid for specific roasters, e.g., roguewave cannot exclude espresso because all coffees have it,
      and also be able to do something like `gesha cart roguewave +espresso`
- [ ] there's a mismatch between commands where you can do `gesha cart 94celcius` but can't do `gesha list --roaster 94celcius`, you have to do `gesha list --roaster 94`
- [ ] zaandklo: roaster name is confusing to use, zaandklo doesn't work for "gesha list --roaster zaandklo"

---

# All good
- [x] 94celcius
- [x] angry
- [x] artery
- [x] cafepista
- [x] colorfull
- [x] demello
- [x] escape
- [x] ethica
- [x] houseoffunk: free shipping is set to 1025 lol
- [x] jungle
- [x] kohi
- [x] monogram
- [x] narval
- [x] nektar
- [x] nucleus
- [x] pirates
- [x] portebleue
- [x] quietly
- [x] rabbithole
- [x] roguewave
- [x] september
- [x] sipstruck
- [x] subtext
- [x] traffic
- [x] zaandklo (process and origin are only in an image so can't parse)