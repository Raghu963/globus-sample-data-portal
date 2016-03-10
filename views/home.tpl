<!-- Page Header -->
<!-- Set background image for this header on the line below. -->
<header class="intro-header" style="background-image: url({{get_url('static', filename='img/home-bg.jpg')}})">
  <div class="container">
    <div class="row">
      <div class="col-lg-8 col-lg-offset-2 col-md-10 col-md-offset-1">
        <div class="site-heading">
          <h1>Modern Research Data Portal</h1>
          <hr class="small">
          <span class="subheading">It's how research data management is done!</span>
        </div>
      </div>
    </div>
  </div>
</header>

<!-- Main Content -->
<div class="container">
  <div class="row">
    <div class="col-lg-8 col-lg-offset-2 col-md-10 col-md-offset-1">
      <div class="post-preview">
        <a href="https://docs.globus.org/api/transfer/" target="_blank">
          <h2 class="post-title">Globus Transfer API</h2>
          <h3 class="post-subtitle">API reference for transfer and sharing functions.</h3>
        </a>
      </div>
      <hr />
      <div class="post-preview">
        <a href="#" target="_blank">
          <h2 class="post-title">Globus Auth API</h2>
          <h3 class="post-subtitle">API reference for authentication and authorization.</h3>
        </a>
      </div>
      <hr />
      <div class="post-preview">
        <a href="https://docs.globus.org/faq/" target="_blank">
          <h2 class="post-title">Frequently Asked Questions</h2>
          <h3 class="post-subtitle">When all else fails...</h3>
        </a>
      </div>
      <hr />

      <!-- Pager -->
      <ul class="pager">
        <li class="next">
          <a href="https://docs.globus.org/" target="_blank">Learn more &rarr;</a>
        </li>
      </ul>
    </div>
  </div>
</div>
<hr />

%rebase('views/base', title='MRDP - Home')
