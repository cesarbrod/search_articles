# LinkedIn Articles — TODO

> When returning to this project, review this list and ask the user if anything should be added or reprioritized before starting work.

---

## 1. Make sure code on the article is properly wrapped whem viewed on epub

Actual behavior:

Now code on Linkedin Articles, identified as an element such as

<pre class="reader-text-block__code-block"><code><!---->CODE TEXT IS HERE<!----></code></pre>

does not wrap properly on the generated ebook, resulting in a quite ugly, one line, display, not suitable for printing.

Expected behavior:

Code expressed on the ebook must be displayed on a text box, using a fixed font in white bold under a dark nlue background.

---

## 2. Add images at the top of the articles to the ebook, right below the article title

Actual behavior:

The banner image, identified on the html code right below the <header aria-label="Article header">
is not imported to the ebook

<figure class="relative">
        <div class="reader-cover-image__wrapper-right-rail-layout">
          <img src="IMG URL" loading="lazy" alt="IMG ALT" id="ember33" class="reader-cover-image__img evi-image lazy-image ember-view">
        </div>
          <figcaption itemprop="caption" class="reader-cover-image__caption">
            IMG CAPTION
          </figcaption>
      </figure>

Expected behavior:

Make sure the image is imported and shown on the ebook, properly resized (not cropped). The image must be shown right below the article title on the ebook.

---

## 3. Prompt on return

When returning to this project, **always read this file first** and ask the user:
> "Here is the current TODO list. Would you like to add, remove, or reprioritize anything before we start?"

---

## 4. Keep `features.md` up to date

After completing any item above, update `features.md` to reflect the new state of the project.

---

## 5. Keep `README.md` up to date

After completing any item above, update `README.md` to reflect the new state of the project.

---

## Completed items (for reference)

- ✅ Smarter sync (stops at first known article)
- ✅ Auto-fetch content for new articles on startup
- ✅ HTML content storage with embedded images (offline-first)
- ✅ Article reader at `/article/<id>`
- ✅ Date extraction — `fix_dates.py` + automatic on future fetches
- ✅ Search snippets show plain text (HTML stripped)
- ✅ Better ePub CSS for `<pre>`/`<code>` blocks
- ✅ Scoped image filenames in ePub (`art_{idx}_img_{n}.ext`)
- ✅ Select and reorder articles before generating ePub
