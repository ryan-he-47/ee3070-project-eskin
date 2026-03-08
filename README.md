# ee3070-project-eskin

a repository for project design coures ee3070, in cityuhk





最后还是用了王主席定义的midi结构体，因为我(和D老师)仔细读了一下esp32\_host\_midi的库，发现它没有实现直接传入midieventdata给发送层的功能，实际使用效果和自定义的结构体差不多，而且里面定义的类型不适合用队列传输。

另外，潘总和王主席的结构体定义非常相似，估计潘总的代码改改就能用，记得都封装好别丢个.ino上来，谢谢

好消息是esp32这端不需要使用esp32\_host\_midi库了，坏消息是潘总可能还是得捋一捋p4转发32的midi信号到usb\_host输出需不需要用这个库。

