import Map "mo:core/Map";
import Array "mo:core/Array";
import Iter "mo:core/Iter";
import Types "../types/trading";
import MockData "mock_data";
import Nat "mo:core/Nat";

module {

  public type NewsStore = Map.Map<Text, Types.NewsArticleRef>;

  // ─── Read ──────────────────────────────────────────────────────────────────

  // Return a paginated slice of all stored articles sorted by published_at desc.
  public func get_all_news(
    store     : NewsStore,
    page      : Nat,
    page_size : Nat,
  ) : [Types.NewsArticleRef] {
    let all = store.toArray();
    // sort by published_at descending (second element of tuple is the article)
    let sorted = all.sort(
      func((_, a), (_, b)) {
        if (a.published_at > b.published_at) #less
        else if (a.published_at < b.published_at) #greater
        else #equal
      },
    );
    let start = page * page_size;
    let total = sorted.size();
    if (start >= total) return [];
    let end_ = Nat.min(start + page_size, total);
    let slice = sorted.sliceToArray(start, end_);
    slice.map<(Text, Types.NewsArticleRef), Types.NewsArticleRef>(
      func((_, art)) = art,
    )
  };

  // Lookup a single article by its id.
  public func get_news_by_id(
    store : NewsStore,
    id    : Text,
  ) : ?Types.NewsArticleRef {
    store.get(id)
  };

  // Return total number of stored articles.
  public func get_total_count(store : NewsStore) : Nat {
    store.size()
  };

  // Filter articles by optional symbol, category, and minimum impact score.
  public func filter_news(
    store      : NewsStore,
    symbol     : ?Text,
    category   : ?Text,
    min_impact : ?Float,
  ) : [Types.NewsArticleRef] {
    let all = store.values().toArray();
    all.filter<Types.NewsArticleRef>(
      func(art) {
        let sym_ok = switch (symbol) {
          case null true;
          case (?s) {
            art.affected_symbols.find<Text>(func(t) = t == s) != null
          };
        };
        let cat_ok = switch (category) {
          case null true;
          case (?c) art.news_category == c;
        };
        let impact_ok = switch (min_impact) {
          case null true;
          case (?mi) art.impact_score >= mi;
        };
        sym_ok and cat_ok and impact_ok
      },
    )
  };

  // ─── Write ─────────────────────────────────────────────────────────────────

  // Upsert an article into the store.
  public func upsert_article(
    store   : NewsStore,
    article : Types.NewsArticleRef,
  ) : () {
    store.add(article.id, article)
  };

  // Load all mock articles into the store and return a status message.
  public func load_mock_data(store : NewsStore) : Text {
    let articles = MockData.get_mock_articles();
    for (art in articles.values()) {
      store.add(art.id, art);
    };
    "Loaded " # articles.size().toText() # " mock articles"
  };

};
