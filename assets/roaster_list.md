- [ ] "gesha list" has a whole bunch of useless options, it should just do either gesha list roaster or gesha list id based on what argument is passed
- [ ] would be useful to have the opposite of gesha cart, like gesha non-cart lol, where it lists the coffees that were excluded and the reason why
    and/or, when you go "gesha cart roaster", it should show both a cart of coffees included and those excluded, so run both commands
- [ ] the free shipping line says "Estimated free-shipping threshold: $60.00 (live policy page)" -- it should clearly say whether it's estimated or fetched lol, not both
- [ ] would be cool to either hardcode some keywords to avoid for specific roasters, e.g., roguewave cannot exclude espresso because all coffees have it, and also be able to do something like `gesha cart roguewave +espresso`
- [ ] there's a mismatch between commands where you can do `gesha cart 94celcius` but can't do `gesha list --roaster 94celcius`, you have to do `gesha list --roaster 94`


- [ ] roguewave: has espresso in all its descriptions so we skip all coffees
- [x] houseoffunk
- [x] quietly
- [ ] kohi; notes are simply "classic" or "funky" lol. The issue is that the notes are in the raw json data, and I'm not sure how to specify the way to get there:

=== RAW JSON DATA ===
{
  "id":8280273485868,
  "title":"ROYAL CASSIS (Kenya)",
  "handle":"royal-cassis-kenya",
  "description":"\u003cp\u003eProfile: FUNKY\u003c\/p\u003e\n\u003cp class=\"p1\"\u003e\u003cem\u003eNotes de dégustation\u003c\/em\u003e: BLACKCURRANT, BUN, HONEY\u003c\/

- [x] subtext
- [ ] artery: bunch of tasting notes in origin
- [x] ethica
- [x] rabbithole
- [x] escape
- [x] pirates
- [ ] 94celcius: list is working but cart isn't; see issue above, it might be relevant
- [x] cafepista
- [ ] jungle: we're just scraping the funky section, but maybe we should scrape all coffees?
     -- need to use https://junglelivraisoncafe.com/collections/classics, which is all coffees
- [ ] zaandklo: missing process
- [ ] nektar: cart not returning anything, not sure why
- [x] september
- [x] monogram
- [ ] narval: missing process and origin
- [ ] [ambros](https://ambroscoffee.com/): Shopify, but product metadata is still too inconsistent for a clean shared parser config.
- [ ] nucleus: Shopify, but the useful coffee catalog spans multiple collections and needs a multi-collection plan
    - actually let's just use https://nucleuscoffee.com/collections/lab-cafe
- [ ] [sipstruck](https://sipstruck.com/): Shopify, but title/notes parsing needs a source-specific shape before it is safe to list.
