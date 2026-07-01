- [ ] "gesha list" has a whole bunch of useless options, it should just do either gesha list roaster or gesha list id based on what argument is passed
- [ ] would be useful to have the opposite of gesha cart, like gesha non-cart lol, where it lists the coffees that were excluded and the reason why
      and/or, when you go "gesha cart roaster", it should show both a cart of coffees included and those excluded, so run both commands
- [ ] gesha roaster should run the scrape, the list, and the cart
- [ ] the free shipping line says "Estimated free-shipping threshold: $60.00 (live policy page)" -- it should clearly say whether it's estimated or fetched lol, not both
- [ ] would be cool to either hardcode some keywords to avoid for specific roasters, e.g., roguewave cannot exclude espresso because all coffees have it, and also be able to do something like `gesha cart roguewave +espresso`
- [ ] there's a mismatch between commands where you can do `gesha cart 94celcius` but can't do `gesha list --roaster 94celcius`, you have to do `gesha list --roaster 94`
---

# All good

- [x] angry
- [x] demello
- [x] traffic
- [x] portebleue
- [x] colorfull
- [x] roguewave
- [x] houseoffunk: free shipping is set to 1025 lol
- [x] quietly
- [x] kohi
- [x] subtext
- [x] artery
- [x] ethica
- [x] rabbithole
- [x] escape
- [x] pirates
- [x] jungle: we're just scraping the funky section, but maybe we should scrape all coffees?
- [x] cafepista
- [x] september
- [x] monogram
- [x] narval

# Issues

- [ ] 94celcius: list is working but cart isn't; see issue above, it might be relevant
- [ ] zaandklo: missing process
- [ ] nektar: cart not returning anything, not sure why

# Still to implement
- [ ] [ambros](https://ambroscoffee.com/): Shopify, but product metadata is still too inconsistent for a clean shared parser config.
- [ ] nucleus: Shopify, but the useful coffee catalog spans multiple collections and needs a multi-collection plan
    - actually let's just use https://nucleuscoffee.com/collections/lab-cafe
- [ ] [sipstruck](https://sipstruck.com/): Shopify, but title/notes parsing needs a source-specific shape before it is safe to list.
