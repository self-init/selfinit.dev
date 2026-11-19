// Click (or Enter/Space on) an image in a post to see it enlarged over a
// darkened page, with its caption underneath. Click anywhere outside the
// caption, press Esc, or use the close button to dismiss.
(function () {
  'use strict';

  var images = document.querySelectorAll('.prose img');
  if (!images.length || typeof HTMLDialogElement === 'undefined') return;

  var dialog = document.createElement('dialog');
  dialog.className = 'lightbox';
  dialog.setAttribute('aria-label', 'Enlarged image');
  dialog.innerHTML =
    '<button type="button" class="lightbox__close" aria-label="Close">×</button>' +
    '<figure class="lightbox__figure"><img class="lightbox__image" alt="">' +
    '<figcaption class="lightbox__caption"></figcaption></figure>';
  document.body.appendChild(dialog);

  var big = dialog.querySelector('.lightbox__image');
  var caption = dialog.querySelector('.lightbox__caption');
  var opener = null;

  function open(src, alt, captionHTML, from) {
    opener = from;
    big.src = src;
    big.alt = alt || '';
    caption.innerHTML = captionHTML || '';
    caption.hidden = !captionHTML;
    dialog.showModal();
  }

  function openImage(img) {
    var figcaption = img.closest('figure') && img.closest('figure').querySelector('figcaption');
    open(img.currentSrc || img.src, img.alt, figcaption && figcaption.innerHTML, img);
  }

  dialog.addEventListener('click', function (event) {
    // Links in the caption still work; anything else closes.
    if (!event.target.closest('.lightbox__caption a')) dialog.close();
  });
  dialog.addEventListener('close', function () {
    big.removeAttribute('src');
    if (opener) opener.focus();
  });

  images.forEach(function (img) {
    if (img.closest('a')) return; // linked images keep their link
    img.classList.add('zoomable');
    img.tabIndex = 0;
    img.setAttribute('role', 'button');
    img.setAttribute('aria-label', 'Enlarge image' + (img.alt ? ': ' + img.alt : ''));
    img.addEventListener('click', function () { openImage(img); });
    img.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openImage(img);
      }
    });
  });
})();
