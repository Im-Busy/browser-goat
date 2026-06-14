# Homebrew formula for browsing-meta
#
# To install (once published):
#   brew install browsing-meta
#
# For tap installation:
#   brew tap Im-Busy/browsing-meta
#   brew install browsing-meta

class BrowsingMeta < Formula
  include Language::Python::Virtualenv

  desc "Meta-layer search intelligence wrapping SearXNG"
  homepage "https://github.com/Im-Busy/browsing-meta"
  url "https://github.com/Im-Busy/browsing-meta/archive/refs/tags/v0.1.0.tar.gz"
  # sha256: ""  # Run `shasum -a 256 v0.1.0.tar.gz` after release and fill in
  license "MIT"
  head "https://github.com/Im-Busy/browsing-meta.git", branch: "main"

  depends_on "python@3.13"

  def install
    virtualenv_install_with_resources
  end

  test do
    system "#{bin}/browsing-meta", "--help"
  end
end
