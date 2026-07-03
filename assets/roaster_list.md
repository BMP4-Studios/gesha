# NICE TO HAVE
- [ ] in _extract_variants, `weight_grams` and `bag_size` can have wildly different values just from the roaster. 
      We need tests to catch these and figure out which one is valid
- [ ] pretty sure the shipping policy is fetched when we call cart -- this should be done when we scrape and stored in the DB
- [ ] would be useful to have the opposite of gesha cart, like gesha non-cart lol, where it lists the coffees that were excluded and the reason why
      and/or, when you go "gesha cart roaster", it should show both a cart of coffees included and those excluded, so run both commands
- [ ] gesha roaster should run the scrape, the list, and the cart
- [ ] Some roasters, e.g., roguewave, have espresso for pretty much all coffees, so we need a way for these to allow the disallowed keywords
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