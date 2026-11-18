class Phylax < Formula
  desc "Back up Claude Code context and folders to your own Google Drive, encrypted"
  homepage "https://github.com/agentnetes/phylax"
  url "https://github.com/agentnetes/phylax/releases/download/v1.0.2/phylax-1.0.2.tar.gz"
  sha256 "3c134482d8513a5ceb9a91aae4d7aaf425f29938334575ad3a360d350bbf2f92"
  license "FSL-1.1-ALv2"
  depends_on "python"
  depends_on "rclone"
  depends_on "age"
  depends_on "gum"

  def install
    libexec.install Dir["*"]
    (bin/"phylax").write <<~EOS
      #!/bin/sh
      exec "#{Formula["python"].opt_bin}/python3" "#{opt_libexec}/phylax.py" "$@"
    EOS
  end

  def caveats
    "Run `phylax setup` to connect Google Drive and create your encryption key."
  end

  test do
    assert_match "phylax", shell_output("#{bin}/phylax --help")
  end
end
